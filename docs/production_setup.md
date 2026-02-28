# 🚀 Wazuh Rule Distribution (WRD) API — Production Deployment Guide

This document provides a detailed, step-of-step guide on how to correctly start and manage the **Production Stack** for the WRD API.

---

## 🏗️ 1. Environment Preparation

Ensure you are working within the production deployment directory:
```bash
cd deployments/docker/
```

Confirm that the necessary configuration files are present:
- `docker-compose.yml`
- `Dockerfile` (for the API)
- `.env` (contains DB credentials and secrets)

---

## 🌐 2. Network Interfaces

Understanding which IP to use is critical for connectivity:

| Interface           | IP / Hostname             | Use Case                                                                                                      |
| ------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **Localhost**       | `localhost` / `127.0.0.1` | Used ONLY for commands run directly on the server (e.g., `curl` from the host CLI).                           |
| **Docker Bridge**   | `172.17.0.1`              | **CRITICAL:** Use this inside Wazuh containers (Worker/Master) to talk to the WRD API via the Docker Gateway. |
| **External/Public** | `YOUR_SERVER_IP`          | Used by remote machines or browser-based tools (like Swagger UI) to access the API.                           |

---

## 🛳️ 3. Starting the Stack

To start the production services (Nginx, API, Postgres) in the background:

```bash
docker-compose up -d
```

### Services Breakdown:
- **`wrd-nginx`**: Handles HTTPS termination (Port 8443) and routes traffic to the API.
- **`docker-wazuh-api-1`**: The core Python API (FastAPI) handling rules and nodes.
- **`wrd-postgres`**: The database storing clusters, nodes, and keys.

---

## 🔑 3. Initializing the API

Once the containers are running, you must initialize the administrator and cluster data.

### Step A: Generate Admin Key
This key is required for all management operations (creating clusters, registering nodes).

```bash
docker exec -it docker-wazuh-api-1 \
  python scripts/init_multi_node.py --create-admin --admin-name "admin"
```
**Important:** Capture the `admin_xxxxxxxx` key generated in the output and store it safely.

### Step B: Register the Wazuh Cluster
```bash
curl -k -X POST "https://localhost:8443/api/v1/clusters" \
  -H "Authorization: Bearer <YOUR_ADMIN_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"name":"multi-node-cluster", "topology_type":"master-worker"}'
```

---

## 🛰️ 4. Registering a Wazuh Node

To add a Wazuh worker or master to the distribution system:

```bash
curl -k -X POST "https://localhost:8443/api/v1/clusters/multi-node-cluster/nodes" \
  -H "Authorization: Bearer <YOUR_ADMIN_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"node_id":"worker-01", "node_type":"worker"}'
```
**Capture the returned `api_key`.** You will need this for the `wrd-sync.sh` script on the Wazuh node.

---

## 🛠️ 5. Troubleshooting Methods

### 📜 Viewing Logs
The most important step in troubleshooting is checking the container logs.

- **Check API logs:** `docker logs -f docker-wazuh-api-1`
- **Check DB logs:** `docker logs -f wrd-postgres`
- **Check Sync script logs (on Wazuh node):** `docker exec <wazuh-container> cat /var/log/wrd-sync.log`

### ❌ Common Issues & Fixes

#### 1. "Invalid API Key" Error
- **Symptom:** Worker sync log shows `{"detail":"Invalid API key"}`.
- **Cause:** Usually code in `src/api/deps.py` incorrectly checking the `api_keys` table instead of the node's `cluster_nodes` table.
- **Fix:** Ensure the `NodeAuthKey` hotfix is applied (see your hotfix documentation).

#### 2. Rules Not Updating
- **Symptom:** New rules are present on GitHub but not on the Wazuh node.
- **Cause:** Syntax check failed on the ruleset.
- **Fix:** Run `/var/ossec/bin/wazuh-analysisd -t` manually inside the Wazuh container to see exact syntax errors (e.g., missing `if_sid`).

#### 3. Database Connection Refused
- **Symptom:** API container exits or logs show "Connection refused" to Postgres.
- **Cause:** The database container is still initializing.
- **Fix:** Wait 30 seconds and restart the API: `docker-compose restart wazuh-api`.

#### 4. Nginx 502 Bad Gateway
- **Symptom:** Browsing to `https://localhost:8443` returns 502.
- **Cause:** The API container is down or starting slowly.
- **Fix:** Check `docker ps` and `docker logs docker-wazuh-api-1`.

---

## 📦 6. Manual Verification Check
To verify the database status of your nodes directly:
```bash
docker exec wrd-postgres sh -c "PGPASSWORD=YOUR_DB_PASS psql -U api -d wazuh_api \
  -c 'SELECT node_id, sync_status, updated_at FROM cluster_nodes;'"
```
If `sync_status` says `success`, your automation is working perfectly!
