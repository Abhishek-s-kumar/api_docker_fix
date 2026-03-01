# 📘 Making `wrd-sync.sh` Persistent — Complete Step-by-Step Guide

---

## 🖥️ Environment Overview

### Machines Involved

| Role                  | Hostname                 | IP Address          | OS               | Details                                    |
| --------------------- | ------------------------ | ------------------- | ---------------- | ------------------------------------------ |
| **Developer / Admin** | `DESKTOP-XXXX` (Windows) | `10.21.235.X` (LAN) | Windows 11       | Your local machine running VS Code and SSH |
| **Linux Server**      | `workshop`               | `10.21.235.82`      | Ubuntu 24.04 LTS | Hosts all Docker containers                |

### Docker Containers on `workshop@10.21.235.82`

| Container Name              | Role                | Image                              | Network              |
| --------------------------- | ------------------- | ---------------------------------- | -------------------- |
| `multi-node-wazuh.master-1` | Wazuh Master Node   | `wazuh/wazuh-manager:4.14.2`       | `multi-node_default` |
| `multi-node-wazuh.worker-1` | Wazuh Worker Node   | `wazuh-worker-wrd:4.14.2` (custom) | `multi-node_default` |
| `docker-wazuh-api-1`        | WRD API (FastAPI)   | Custom built                       | `docker_default`     |
| `wrd-nginx`                 | HTTPS Reverse Proxy | `nginx:latest`                     | `docker_default`     |
| `wrd-postgres`              | PostgreSQL Database | `postgres:15`                      | `docker_default`     |

---

## 🌐 Network Interface Reference

| Interface                 | IP / Hostname               | When to Use                                                                       |
| ------------------------- | --------------------------- | --------------------------------------------------------------------------------- |
| `localhost` / `127.0.0.1` | Linux server local loopback | When running `curl` from inside `workshop` host terminal                          |
| `172.17.0.1`              | Docker bridge gateway IP    | **IMPORTANT:** Use this inside any Docker container to reach services on the host |
| `10.21.235.82`            | Server's LAN IP             | When connecting from Windows machine or an external machine                       |
| `0.0.0.0:8443`            | Port bound by `wrd-nginx`   | Accessible from any interface on the server                                       |

> ⚠️ The `wrd-sync.sh` script inside the Wazuh worker container uses `172.17.0.1:8443` to reach the WRD API — **never use `localhost`** from a container.

---

## 🔑 Credentials Reference (Example/Dummy Values)

| Item                         | Value                                                                |
| ---------------------------- | -------------------------------------------------------------------- |
| SSH user                     | `workshop`                                                           |
| SSH password                 | `Pas$@123`                                                           |
| SSH host                     | `10.21.235.82`                                                       |
| PostgreSQL user              | `api`                                                                |
| PostgreSQL password          | `3wKtDihz+mCAn4nAaVnBxYZbuAVww8y8`                                   |
| PostgreSQL database          | `wazuh_api`                                                          |
| WRD Admin API Key            | `admin_AbCdEfGhIjKlMnOpQrStUvWx`                                     |
| WRD Node API Key (worker-01) | `node_multi-node-cluster_worker-01_WnK8SkRu8gkPPenyqPNf9j2s2uPlRood` |

---

## 📁 Directory Structure Created

These files are placed **next to** your Wazuh multi-node `docker-compose.yml`:

```
~/wazuh-docker/multi-node/
├── docker-compose.yml        ← patched to use custom worker image
├── wazuh-worker/             ← NEW folder (build context)
│   ├── Dockerfile            ← custom image definition
│   ├── wrd-sync.sh           ← the sync script baked into the image
│   └── docker-entrypoint.sh  ← starts cron before Wazuh /init
```

---

## 🛠️ Step-by-Step Instructions

### STEP 1 — Connect to the Linux Server

From your **Windows machine**, open a terminal (PowerShell):

```bash
ssh workshop@10.21.235.82
# Password: Pas$@123
```

---

### STEP 2 — Find Your Wazuh Multi-Node Directory

```bash
COMPOSE_FILE=$(docker inspect multi-node-wazuh.worker-1 \
  --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}')
COMPOSE_DIR=$(dirname "$COMPOSE_FILE")
echo "Working directory: $COMPOSE_DIR"
```

Expected output:
```
Working directory: /root/wazuh-docker/multi-node
```

---

### STEP 3 — Create the `wazuh-worker` Build Context Directory

```bash
mkdir -p "$COMPOSE_DIR/wazuh-worker"
cd "$COMPOSE_DIR/wazuh-worker"
```

---

### STEP 4 — Create `wrd-sync.sh`

This is the script that runs inside the Wazuh worker every 5 minutes. It downloads rules from GitHub, validates syntax, and reports status to the WRD API.

```bash
cat << 'EOF' > /path/to/wazuh-worker/wrd-sync.sh
#!/bin/bash
# ============================================================
# WRD (Wazuh Rule Distribution) Sync Script
# ============================================================

NODE_ID="worker-01"
API_KEY="node_multi-node-cluster_worker-01_WnK8SkRu8gkPPenyqPNf9j2s2uPlRood"

# IMPORTANT: Use Docker bridge IP (172.17.0.1) NOT localhost
API_URL="https://172.17.0.1:8443"
RULES_DIR="/var/ossec/etc/rules"
LOG_FILE="/var/log/wrd-sync.log"
GITHUB_BASE="https://raw.githubusercontent.com/YOUR_ORG/DaC/main/rules"
RULE_FILES=("local_rules.xml" "0200-sigma_rules.xml")

echo "$(date) - Starting sync on ${NODE_ID}" >> "$LOG_FILE"

for filename in "${RULE_FILES[@]}"; do
  echo "$(date) - Downloading $filename" >> "$LOG_FILE"
  curl -fsSL "${GITHUB_BASE}/${filename}" -o "${RULES_DIR}/${filename}" 2>> "$LOG_FILE"
  if [ $? -ne 0 ]; then
    echo "$(date) - WARNING: Failed to download $filename" >> "$LOG_FILE"
    rm -f "${RULES_DIR}/${filename}"
  fi
done

echo "$(date) - Checking syntax..." >> "$LOG_FILE"
/var/ossec/bin/wazuh-analysisd -t >> "$LOG_FILE" 2>&1
SYNTAX_EXIT=$?

if [ $SYNTAX_EXIT -eq 0 ]; then
  echo "$(date) - Restarting wazuh-manager!" >> "$LOG_FILE"
  /var/ossec/bin/wazuh-control restart >> "$LOG_FILE" 2>&1
  SYNC_STATUS="success"
else
  echo "$(date) - Syntax check failed, skip restart!" >> "$LOG_FILE"
  SYNC_STATUS="failed"
fi

RESPONSE=$(curl -k -s -X POST "${API_URL}/api/v1/nodes/${NODE_ID}/status" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"status\":\"${SYNC_STATUS}\"}")
echo "$(date) - API response: ${RESPONSE}" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
EOF

chmod +x wrd-sync.sh
```

---

### STEP 5 — Create `docker-entrypoint.sh`

This script starts the cron daemon **before** handing off to Wazuh's built-in `/init` script.

```bash
cat << 'EOF' > /path/to/wazuh-worker/docker-entrypoint.sh
#!/bin/bash
# Start cron daemon in background (for wrd-sync cron job)
service cron start

# Run the default Wazuh entrypoint
exec /init
EOF

chmod +x docker-entrypoint.sh
```

---

### STEP 6 — Create the `Dockerfile`

> ⚠️ Wazuh 4.14.2 is based on **Amazon Linux** — use `yum`, NOT `apt-get`.

```bash
cat << 'EOF' > /path/to/wazuh-worker/Dockerfile
# Custom Wazuh Worker Image with WRD Sync Script
FROM wazuh/wazuh-manager:4.14.2

# Install cronie (cron daemon for Amazon Linux)
RUN yum install -y cronie && yum clean all

# Copy the WRD sync script into the image
COPY wrd-sync.sh /usr/local/bin/wrd-sync.sh
RUN chmod +x /usr/local/bin/wrd-sync.sh

# Install the cron job — runs every 5 minutes
RUN echo "*/5 * * * * root /usr/local/bin/wrd-sync.sh" > /etc/cron.d/wrd-sync && \
    chmod 0644 /etc/cron.d/wrd-sync

# Use our custom entrypoint that starts cron first
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
EOF
```

---

### STEP 7 — Build the Custom Docker Image

From the `wazuh-worker/` directory:

```bash
cd "$COMPOSE_DIR/wazuh-worker"
docker build -t wazuh-worker-wrd:4.14.2 .
# Expected: Successfully built xxxx && Successfully tagged wazuh-worker-wrd:4.14.2
```

To verify the image was created:
```bash
docker images | grep wazuh-worker-wrd
```

---

### STEP 8 — Update `docker-compose.yml`

Find the `wazuh.worker` service in your compose file and update it to:

```yaml
wazuh.worker:
  image: wazuh-worker-wrd:4.14.2        # ← our custom image
  build:                                  # ← build from our Dockerfile
    context: ./wazuh-worker
    dockerfile: Dockerfile
  # ... (all other existing settings remain unchanged)
```

To apply the change in place (using `sed`):
```bash
# Find the line number of the worker image
LAST_LINE=$(grep -n "image: wazuh/wazuh-manager:4.14.2" "$COMPOSE_FILE" | tail -1 | cut -d: -f1)

# Replace it with custom image + build directive
sed -i "${LAST_LINE}s|image: wazuh/wazuh-manager:4.14.2|image: wazuh-worker-wrd:4.14.2\n    build:\n      context: ./wazuh-worker\n      dockerfile: Dockerfile|" "$COMPOSE_FILE"
```

---

### STEP 9 — Redeploy the Worker Container

```bash
cd "$COMPOSE_DIR"
docker compose up -d --no-deps wazuh.worker
```

> The `--no-deps` flag updates ONLY the worker without touching the master node or other services.

---

### STEP 10 — Verify Everything is Working

```bash
# 1. Confirm worker is using our custom image
docker inspect multi-node-wazuh.worker-1 --format '{{.Config.Image}}'
# Expected: wazuh-worker-wrd:4.14.2

# 2. Confirm wrd-sync.sh exists in the container
docker exec multi-node-wazuh.worker-1 ls -lah /usr/local/bin/wrd-sync.sh
# Expected: -rwxr-xr-x root root ... /usr/local/bin/wrd-sync.sh

# 3. Confirm cron job is installed
docker exec multi-node-wazuh.worker-1 cat /etc/cron.d/wrd-sync
# Expected: */5 * * * * root /usr/local/bin/wrd-sync.sh

# 4. Run sync manually to test
docker exec multi-node-wazuh.worker-1 /usr/local/bin/wrd-sync.sh

# 5. View the sync log
docker exec multi-node-wazuh.worker-1 tail -20 /var/log/wrd-sync.log

# 6. Check the database updated the sync status
docker exec wrd-postgres sh -c "PGPASSWORD=3wKtDihz+mCAn4nAaVnBxYZbuAVww8y8 \
  psql -U api -d wazuh_api \
  -c \"SELECT node_id, sync_status, updated_at FROM cluster_nodes WHERE node_id='worker-01';\""
# Expected: worker-01 | success | <timestamp>
```

---

## 🔄 What Happens After a Full Redeploy

```bash
docker compose down
docker compose up -d
```

The worker will:
1. Start from `wazuh-worker-wrd:4.14.2` (our custom image)
2. Launch cron daemon automatically via `docker-entrypoint.sh`
3. Start Wazuh via `/init`
4. Within 5 minutes, cron will fire `wrd-sync.sh` automatically

**No manual injection needed. Everything is in the image.** ✅

---

## 🚨 Troubleshooting

| Problem                                    | Cause                                                     | Fix                                                              |
| ------------------------------------------ | --------------------------------------------------------- | ---------------------------------------------------------------- |
| `apt-get: command not found` during build  | Wrong package manager — Wazuh is Amazon Linux, not Debian | Use `yum install -y cronie`                                      |
| `{"detail":"Invalid API key"}` in sync log | API auth bug — endpoint checks wrong DB table             | Apply `NodeAuthKey` hotfix to `deps.py`                          |
| cron not running after redeploy            | `service cron start` not called                           | Verify `docker-entrypoint.sh` is copied and used as `ENTRYPOINT` |
| Rules not updating                         | Syntax check failure due to bad `if_sid` references       | Check `wazuh-analysisd -t` output in `/var/log/wrd-sync.log`     |
| sync log empty                             | cron daemon not started                                   | Run `service cron status` inside container                       |
