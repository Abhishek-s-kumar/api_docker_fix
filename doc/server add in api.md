# 🔷 WRD API Node Integration Guide & Troubleshooting

Perfect 👍 Here is a clean, production-safe, step-by-step guide using your exact running containers.

You currently have:
* `wrd-nginx` (port 8443 exposed)
* `docker-wazuh-api-1`
* `wrd-postgres`

So your API endpoint is:
`https://localhost:8443`

*(If another machine connects, replace `localhost` with your server IP.)*

---

## ✅ STEP 0 — Make Sure Admin & Node Keys Exist
Instead of manually injecting SQL to create the cluster and node, the `init_multi_node.py` script has been upgraded to handle this automatically!

First, check if the admin key exists:
```bash
docker exec -it docker-wazuh-api-1 cat /data/admin_key.txt
```

If it exists, save it! If not, or if you are running this natively in a fresh environment, initialize the database and the default worker node:
```bash
docker exec -it docker-wazuh-api-1 \
python scripts/init_multi_node.py --create-admin --non-interactive
```

This will automatically seed the `multi-node-cluster` and register the `worker-01` node if they do not already exist.

You will get an output containing:
* **Admin API Key**: `admin_xxxxxxxxxxxxx`
* **Worker-01 API Key**: `node_multi-node-cluster_worker-01_xxxxx`

⚠️ **Important:** Save both keys securely! The Worker API key is shown ONLY ONCE.

---

## ✅ STEP 1 — Configure New Wazuh Worker
On the new Wazuh server (e.g., `multi-node-wazuh.worker-1`), we need a script to pull the raw `.xml` rules directly from your GitHub repository and notify the WRD API of its status.

Create the synchronization script:
```bash
docker exec -it multi-node-wazuh.worker-1 bash -c "mkdir -p /usr/local/bin/ && touch /usr/local/bin/wrd-sync.sh"
```

**Add the following code into `/usr/local/bin/wrd-sync.sh`:**
```bash
#!/bin/bash

API_URL="https://172.17.0.1:8443"
NODE_ID="worker-01"
API_KEY="node_multi-node-cluster_worker-01_xxxxx" # Replace with your generated key
REPO_RAW_URL="https://api.github.com/repos/Abhishek-s-kumar/DaC/contents/rules"
LOG_FILE="/var/log/wrd-sync.log"

echo "$(date) - Starting sync on $NODE_ID" > $LOG_FILE

# Download raw XML files from GitHub
curl -s "$REPO_RAW_URL" | \
grep -o -E "https://raw.githubusercontent.com/[^\"]+\.xml" | while read -r file_url; do
    filename=$(basename "$file_url")
    curl -s -L "$file_url" -o "/var/ossec/etc/rules/$filename"
done

if [ $? -eq 0 ]; then
    # Verify syntax using wazuh-control
    /var/ossec/bin/wazuh-control info >> $LOG_FILE 2>&1
    if [ $? -eq 0 ]; then
        # Restart the Wazuh Manager to apply rules
        /var/ossec/bin/wazuh-control restart >> $LOG_FILE 2>&1
        
        # Report Success to WRD API
        curl -k -s -X POST "$API_URL/api/v1/nodes/$NODE_ID/status" \
             -H "Authorization: Bearer $API_KEY" \
             -H "Content-Type: application/json" \
             -d '{"status":"success"}' >> $LOG_FILE 2>&1
    else
        # Report Syntax Failure to WRD API
        curl -k -s -X POST "$API_URL/api/v1/nodes/$NODE_ID/status" \
             -H "Authorization: Bearer $API_KEY" \
             -H "Content-Type: application/json" \
             -d '{"status":"failed", "message": "Syntax error"}' >> $LOG_FILE 2>&1
    fi
fi
```

Make it executable:
```bash
docker exec -it multi-node-wazuh.worker-1 bash -c "chmod +x /usr/local/bin/wrd-sync.sh"
```

---

## 🔄 STEP 2 — Automate It (Recommended)
To ensure the node syncs automatically every 5 minutes:

**Option A: Manual Installation (Ephemeral)**
```bash
docker exec -it multi-node-wazuh.worker-1 bash -c "apt-get update && apt-get install -y cron curl jq"
docker exec -it multi-node-wazuh.worker-1 bash -c "mkdir -p /etc/cron.d/ && echo '*/5 * * * * root /usr/local/bin/wrd-sync.sh > /proc/1/fd/1 2>&1' > /etc/cron.d/wrd-sync"
docker exec -it multi-node-wazuh.worker-1 bash -c "chmod 0644 /etc/cron.d/wrd-sync && service cron start"
```

**Option B: Custom Dockerfile (Persistent — Best for Deployment)**
Create a custom `Dockerfile` next to your Wazuh docker-compose definition so the sync script and cron survive a redeployment:
```dockerfile
FROM wazuh/wazuh-manager:4.7.2

USER root
# Install prerequisites packages inside Wazuh image
RUN apt-get update && apt-get install -y cron curl jq

# Make sure you copy wrd-sync.sh from the directory beside the Dockerfile! 
COPY wrd-sync.sh /usr/local/bin/wrd-sync.sh
RUN chmod +x /usr/local/bin/wrd-sync.sh

RUN mkdir -p /etc/cron.d/ && \
    echo '*/5 * * * * root /usr/local/bin/wrd-sync.sh > /proc/1/fd/1 2>&1' > /etc/cron.d/wrd-sync && \
    chmod 0644 /etc/cron.d/wrd-sync && \
    crontab /etc/cron.d/wrd-sync

CMD service cron start && /init
```
Update your `docker-compose.yml` to use `build: .` instead of the generic wazuh image.

---

## 🔐 STEP 3 — Important Technical Notes
* **Wazuh Restarts:** Docker containers do not use `systemctl`. You MUST use `/var/ossec/bin/wazuh-control restart` and `/var/ossec/bin/wazuh-control info` to apply and test rules safely.
* **Network Binding:** Containers communicate using the Docker Bridge network. `172.17.0.1` represents the host machine from inside the container when localhost isn't appropriate.
* **GitHub Repository Changes:** If you change your GitHub rules repository in the future, simply update the `REPO_RAW_URL` in `/usr/local/bin/wrd-sync.sh`!
* **API Key Security:** The database stores bcrypt hashes! Meaning API keys cannot be recovered. Ensure you save them safely when `scripts/init_multi_node.py` generates them.

---

🧠 **Complete Flow Summary**
1. Admin runs `init_multi_node.py`
2. WRD auto-seeds the cluster & generates node API key
3. Node executes `wrd-sync.sh` (via cron)
4. Node downloads raw XML from GitHub
5. Node validates syntax via `wazuh-control info`
6. Node applies rules & restarts
7. Node reports telemetry back to WRD API endpoint

🎯 **You Are Now Fully Integrated!**
Your Wazuh node securely manages external rules and reports its health autonomously.
