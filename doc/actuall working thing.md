# 🔷 Wazuh Rule Distribution API — Complete Guide

> **Environment:** `wrd-nginx` (port 8443) · `docker-wazuh-api-1` · `wrd-postgres` · `multi-node-wazuh.worker-1`

---

## 🏗️ Architecture Overview

```
GitHub Repo (rules)
        │
        ▼
  wrd-sync.sh (cron, every 5 min)  ← runs inside Wazuh worker/master containers
        │
        ├─ Downloads rules from GitHub raw URLs
        ├─ Validates syntax with wazuh-analysisd -t
        ├─ Restarts wazuh-control (if valid)
        └─ Reports status to WRD API via POST /api/v1/nodes/{node_id}/status
                    │
                    ▼
         WRD API (docker-wazuh-api-1)
                    │
                    ▼
         PostgreSQL (wrd-postgres) → cluster_nodes table
```

**In a multi-node Wazuh cluster:**
- **Master node** handles cluster coordination and agent registration
- **Worker nodes** handle event analysis and rule processing
- Both should have synchronized rules for consistency
- Rules are pulled independently by each node — there is no push from master to worker

---

## ✅ STEP 0 — Verify Admin Key

```bash
docker exec -it docker-wazuh-api-1 cat /data/admin_key.txt
```

If missing, regenerate:
```bash
docker exec -it docker-wazuh-api-1 \
  python scripts/init_multi_node.py --create-admin --admin-name "admin"
docker exec -it docker-wazuh-api-1 cat /data/admin_key.txt
```

Save this key securely — it's your Admin bearer token for all management operations.

---

## ✅ STEP 1 — Clean Up Duplicate Node Entries (if needed)

> [!WARNING]
> The WRD API currently inserts new rows on each re-registration instead of updating. Run this cleanup if you see duplicate `node_id` rows in the database.

```bash
# Check for duplicates
docker exec wrd-postgres sh -c "PGPASSWORD=YOUR_PG_PASS psql -U api -d wazuh_api \
  -c 'SELECT node_id, COUNT(*) FROM cluster_nodes GROUP BY node_id HAVING COUNT(*) > 1;'"

# Remove duplicates (example for master-01)
docker exec wrd-postgres sh -c "PGPASSWORD=YOUR_PG_PASS psql -U api -d wazuh_api \
  -c \"DELETE FROM cluster_nodes WHERE node_id='master-01';\""
```

---

## ✅ STEP 2 — Register a Cluster and Node

### 2a — Create the cluster (if not exists)

```bash
curl -k -X POST "https://localhost:8443/api/v1/clusters" \
  -H "Authorization: Bearer ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"multi-node-cluster","topology_type":"master-worker"}'
```

### 2b — Register a node

```bash
curl -k -X POST "https://localhost:8443/api/v1/clusters/multi-node-cluster/nodes" \
  -H "Authorization: Bearer ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"node_id":"worker-01","node_type":"worker"}'
```

Save the returned [api_key](file:///d:/New%20folder/project/api%20docker%20ssh/security.py#28-31) — it's the **Node API key** used in the sync script.

### 2c — (Optional) Register master node too

```bash
curl -k -X POST "https://localhost:8443/api/v1/clusters/multi-node-cluster/nodes" \
  -H "Authorization: Bearer ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"node_id":"master-01","node_type":"master"}'
```

> [!TIP]
> For consistency in production, both master and worker should have the same rules synced. Register both nodes and install `wrd-sync.sh` on each.

---

## ✅ STEP 3 — Install the Sync Script on the Wazuh Node

```bash
docker exec -it multi-node-wazuh.worker-1 bash
```

Inside the container:

```bash
cat << 'EOF' > /usr/local/bin/wrd-sync.sh
#!/bin/bash

NODE_ID="worker-01"
API_KEY="node_multi-node-cluster_worker-01_YOUR_KEY"
API_URL="https://172.17.0.1:8443"
RULES_DIR="/var/ossec/etc/rules"
LOG_FILE="/var/log/wrd-sync.log"

GITHUB_BASE="https://raw.githubusercontent.com/YOUR_ORG/YOUR_REPO/main/rules"
RULE_FILES=("local_rules.xml" "0200-sigma_rules.xml")

echo "$(date) - Starting sync on ${NODE_ID}" >> "$LOG_FILE"

for RULE_FILE in "${RULE_FILES[@]}"; do
  echo "$(date) - Downloading ${RULE_FILE}" >> "$LOG_FILE"
  curl -fsSL "${GITHUB_BASE}/${RULE_FILE}" -o "${RULES_DIR}/${RULE_FILE}"
done

echo "$(date) - Checking syntax..." >> "$LOG_FILE"
/var/ossec/bin/wazuh-analysisd -t >> "$LOG_FILE" 2>&1
SYNTAX_EXIT=$?

if [ $SYNTAX_EXIT -eq 0 ]; then
  echo "$(date) - Restarting wazuh-manager!" >> "$LOG_FILE"
  /var/ossec/bin/wazuh-control restart >> "$LOG_FILE" 2>&1
  SYNC_STATUS="success"
  curl -k -s -X POST "${API_URL}/api/v1/nodes/${NODE_ID}/status" \
    -H "Authorization: Bearer ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"status\":\"${SYNC_STATUS}\"}" >> "$LOG_FILE"
else
  echo "$(date) - Syntax check failed, skip restart!" >> "$LOG_FILE"
  SYNC_STATUS="failed"
  curl -k -s -X POST "${API_URL}/api/v1/nodes/${NODE_ID}/status" \
    -H "Authorization: Bearer ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"status\":\"${SYNC_STATUS}\"}" >> "$LOG_FILE"
fi
echo "" >> "$LOG_FILE"
EOF

chmod +x /usr/local/bin/wrd-sync.sh

# Add to cron (every 5 minutes)
echo "*/5 * * * * /usr/local/bin/wrd-sync.sh" | crontab -
```

---

## ✅ STEP 4 — Fix Rules With Missing `if_sid` References

> [!IMPORTANT]
> You saw these warnings in your sync log:
> ```
> WARNING: Signature ID '100100' was not found in the 'if_sid' option of rule '100600'
> WARNING: Empty 'if_sid' value. Rule '100600' will be ignored.
> ```

**Root cause:** Your Sigma rules reference parent rule IDs (e.g. `100100`, `100201`, `100202`) that do not exist on the worker. This means the Sigma rule file downloaded from GitHub but was partially loaded with those rules silently ignored.

**How to fix:** In your GitHub repo (`DaC/rules`), the `0200-sigma_rules.xml` file must reference rule IDs that actually exist in the Wazuh default ruleset OR you must include all the parent rules. Either:

1. Remove the `<if_sid>` lines from child rules that reference unregistered parent IDs, or
2. Add the missing parent rules (IDs `100100`, `100201`, `100202`) as explicit rules in `local_rules.xml`

Also note:
```
WARNING: Rule ID '100001' is duplicated
```
Your `local_rules.xml` and the default Wazuh ruleset both define rule `100001`. Rename your custom rule to an ID above `100000` that isn't already used.

---

## ✅ STEP 5 — Verify Everything is Working

```bash
# 1. Check sync log on worker
docker exec multi-node-wazuh.worker-1 cat /var/log/wrd-sync.log

# 2. Check rule files are present
docker exec multi-node-wazuh.worker-1 ls -lah /var/ossec/etc/rules/

# 3. Verify node status in database
docker exec wrd-postgres sh -c "PGPASSWORD=YOUR_PG_PASS psql -U api -d wazuh_api \
  -c 'SELECT node_id, sync_status, updated_at FROM cluster_nodes ORDER BY updated_at DESC LIMIT 5;'"
```

Expected output:
```
 node_id   | sync_status |          updated_at
-----------+-------------+-------------------------------
 worker-01 | success     | 2026-02-28 12:43:41.168444+00
```

---

## ✅ STEP 6 — Use the Swagger UI

1. Open: **`https://YOUR_SERVER_IP:8443/docs`**
2. Click the 🔒 **Authorize** button (top right)
3. Enter: `Bearer ADMIN_KEY_HERE`
4. You can now call **all API endpoints** interactively:
   - `GET /api/v1/clusters` — list clusters
   - `POST /api/v1/clusters/{name}/nodes` — register a new node
   - `GET /api/v1/nodes/{node_id}/rules` — download rule ZIP
   - `POST /api/v1/nodes/{node_id}/status` — report sync status

---

## 🚨 Troubleshooting Guide

| Symptom | Cause | Fix |
|---|---|---|
| `{"detail":"Invalid API key"}` | API checks wrong DB table for node keys | ✅ Fixed by patching [deps.py](file:///d:/New%20folder/project/api%20docker%20ssh/deps.py) with `NodeAuthKey` dependency |
| Rules file missing after sync | Syntax check fails → script skips those files | Fix the `if_sid` references in your GitHub repo |
| `Rule ID is duplicated` warning | Two rule files define the same ID | Rename your custom rule ID to an unused one |
| `sync_status` stuck on `pending` | Status POST never reaches API | Check cron is running; verify `API_KEY` and `API_URL` in the script |
| 3 duplicate `master-01` rows | API inserts instead of upserts on re-registration | Delete duplicates via SQL (see Step 1) |
| `wazuh-control: command not found` | Wrong binary path in script | Use `/var/ossec/bin/wazuh-control` |
| Syntax check exits with error | Rules reference missing SIDs | Check `wazuh-analysisd -t` locally first before pushing to repo |

---

## 🚀 Persistent Production Deployment

To ensure everything survives a fresh `docker-compose up`:

### WRD API — Auto-seeding
Modified `scripts/init_multi_node.py` now auto-provisions:
- The `multi-node-cluster` cluster
- The `worker-01` node with a pinned API key
- The admin key

So on every fresh deploy: `docker-compose up -d` sets everything up automatically.

### Wazuh Worker — Bake into Dockerfile
Create `deployments/docker/wrd-sync.sh` on your host and add to your `Dockerfile`:

```dockerfile
COPY deployments/docker/wrd-sync.sh /usr/local/bin/wrd-sync.sh
RUN chmod +x /usr/local/bin/wrd-sync.sh && \
    echo "*/5 * * * * /usr/local/bin/wrd-sync.sh" | crontab -
```

> [!NOTE]
> 🛠️ **Applied Hotfix** — `src/api/deps.py` was patched to add `NodeAuthKey` dependency that authenticates node requests against the `cluster_nodes` table. `src/api/v1/nodes.py` was updated to use `NodeAuthKey`. This fix must be committed to your repo and rebuilt into the Docker image for persistence.
