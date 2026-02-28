# WRD API – Wazuh Rules Distribution API

> **Centralized GitOps-based rules management for distributed Wazuh clusters**  
> Version 2.0.0

[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-24.0+-blue)](https://docker.com)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Installation & Configuration](#installation--configuration)
- [Usage Guide](#usage-guide)
- [Wazuh Node Integration](#wazuh-node-integration)
- [API Reference](#api-reference)
- [Development](#development)
- [Makefile Targets](#makefile-targets)
- [Troubleshooting & FAQs](#troubleshooting--faqs)
- [Security Considerations](#security-considerations)
- [License](#license)

---

## Overview

The **WRD API** provides a central control plane for distributing Wazuh rules across multiple Wazuh managers in a cluster. Instead of manually copying rule files to each node, you store your rules in a Git repository, and the API handles versioned, atomic distribution to all registered nodes with support for multiple rollout strategies (rolling, blue‑green, canary). Nodes automatically report their sync status back to the API, giving you a real‑time view of your entire fleet.

**Key Features**
- GitOps workflow: rules are managed in Git, pulled by the API, and pushed to nodes.
- Multi‑cluster support: register multiple Wazuh clusters with master‑worker or single‑node topologies.
- Node authentication: per‑node API keys (hashed with bcrypt) for secure communication.
- Rollout strategies: `rolling`, `blue‑green`, `canary`, `immediate`.
- Status reporting: nodes report success/failure, and the API tracks deployment progress.
- Swagger UI: interactive API documentation at `/docs`.

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   GitHub Repo   │────▶│   WRD API       │────▶│   PostgreSQL    │
│   (rules/*.xml) │     │ (FastAPI)       │     │   (cluster/nodes)│
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                  │
                                  │ (pull rules ZIP)
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Wazuh Cluster                           │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐           │
│  │ master-01  │    │ worker-01  │    │ worker-02  │   ...     │
│  │ (sync.sh)  │    │ (sync.sh)  │    │ (sync.sh)  │           │
│  └────────────┘    └────────────┘    └────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

**Data Flow**
1. An administrator pushes rule changes to the Git repository.
2. The WRD API (optionally on a cron job or manually) pulls the latest rules via `POST /api/v1/rules/sync-git`.
3. A sync is triggered for a cluster (manually or automatically) via `POST /api/v1/clusters/{id}/sync`.
4. Each Wazuh node periodically runs a script (`wrd-sync.sh`) that:
   - Downloads the current rules package (ZIP) from `GET /api/v1/nodes/{node_id}/rules`.
   - Validates syntax with `wazuh-analysisd -t`.
   - Restarts the Wazuh manager (if syntax is OK) and reports the status back to the API via `POST /api/v1/nodes/{node_id}/status`.
5. The API updates the node’s sync status in the database.

---

## Quick Start

Get the WRD API up and running in development mode in five minutes.  
**All commands in this section are executed on your host machine (where Docker is installed).**

```bash
# 1. Clone the repository
git clone https://github.com/Abhishek-s-kumar/wazuh-api-docker.git wazuh-api-docker
cd wazuh-api-docker

# 2. Generate secrets and copy environment template
make secrets
make env

# 3. Start the development stack (hot‑reload enabled)
make up-dev

# 4. Initialize the database and create the first admin API key
make init-admin

# 5. Display the admin key (save it!)
make show-admin-key
```

After the stack starts, you can access:

- **API**: http://localhost:8000 (from your host)
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health check**: http://localhost:8000/health

> **Note for remote access**: If you need to access the API from another machine, replace `localhost` with your server’s IP address (and adjust firewall rules accordingly). In production, the API is exposed via HTTPS on port 8443 through NGINX.

---

## Installation & Configuration

### Prerequisites

- Docker 24.0+ and Docker Compose v2
- `make`, `openssl` (for secret generation)
- Git

### Environment Variables

Copy `.env.example` to `.env` and adjust the values (run on host):

```bash
make env
```

Key variables:

| Variable | Description |
|----------|-------------|
| `ENVIRONMENT` | `development` or `production` |
| `DATABASE_URL` | PostgreSQL async connection string |
| `SECRET_KEY` / `JWT_SECRET` | Used for signing (set via secrets in production) |
| `GIT_REMOTE_URL` | URL of the Git repository containing rules (optional in dev) |
| `GIT_BRANCH` | Branch to track (default `main`) |

### Secrets Management

In production, sensitive values are mounted as Docker secrets. The `Makefile` generates three files inside the `secrets/` directory (run on host):

```bash
make secrets
```

- `secret_key.txt`
- `jwt_secret.txt`
- `db_password.txt`

These are automatically used by the production compose file (`deployments/docker/docker-compose.yml`).

### Docker Compose Profiles

- **Development** (`docker-compose.dev.yml`): single API replica, hot‑reload, ports exposed.
- **Production** (`deployments/docker/docker-compose.yml`): three API replicas behind NGINX, internal networking, secrets.

Use the `Makefile` targets to start the appropriate stack.

---

## Usage Guide

All commands below assume you have the admin API key and are interacting with the WRD API.  
**Where to run**: unless specified otherwise, these commands are intended to be run **on the host machine** (or any machine with network access to the API). For production, use `https://your-server-ip:8443` instead of `localhost`.

### 1. Register a Cluster

You need an **admin API key** (obtained during `make init-admin`). Use it in the `Authorization` header.

```bash
curl -k -X POST "https://localhost:8443/api/v1/clusters" \
  -H "Authorization: Bearer admin_xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "production-emea",
    "topology_type": "master-worker",
    "sites": [
      {
        "name": "frankfurt",
        "node_count": 3,
        "master_node_id": "master-fra",
        "worker_node_ids": ["worker-fra-01", "worker-fra-02"]
      }
    ]
  }'
```

The response contains **plaintext API keys for each node** – store them securely; they will never be shown again.

### 2. Add a Node to an Existing Cluster

If you need to add a node later, use the admin key again:

```bash
curl -k -X POST "https://localhost:8443/api/v1/clusters/production-emea/nodes" \
  -H "Authorization: Bearer admin_xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"node_id": "worker-fra-03", "node_type": "worker", "site": "frankfurt"}'
```

The response includes the new node’s API key.

### 3. Sync Rules from Git

Manually pull the latest rules from your Git repository:

```bash
curl -k -X POST "https://localhost:8443/api/v1/rules/sync-git" \
  -H "Authorization: Bearer admin_xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"branch": "main"}'
```

This updates the local copy of the repository inside the API container.

### 4. Trigger a Cluster Sync

Push the current rules to all nodes in a cluster:

```bash
curl -k -X POST "https://localhost:8443/api/v1/clusters/production-emea/sync" \
  -H "Authorization: Bearer admin_xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"strategy": "rolling", "batch_size": 2}'
```

The API creates a deployment record and begins notifying nodes (via the status endpoint) asynchronously.

### 5. Node Status Reporting (from Wazuh nodes)

This endpoint is called by the `wrd-sync.sh` script on each node. It updates the node’s sync status and last‑seen timestamp.

```bash
curl -k -X POST "https://api.example.com/api/v1/nodes/worker-fra-01/status" \
  -H "Authorization: Bearer node_production-emea_worker-fra-01_xxxxx" \
  -H "Content-Type: application/json" \
  -d '{"status": "success", "deployed_version": "abc123", "rules_count": 42}'
```

> **Note**: This command is normally run **inside the Wazuh container** as part of the sync script. It is shown here only for reference.

### 6. Using the Swagger UI

Navigate to `https://your-server:8443/docs` (from your browser). Click the **Authorize** button and enter your admin API key as `Bearer <key>`. You can then explore and test all endpoints interactively.

---

## Wazuh Node Integration

Each Wazuh manager (master or worker) must run a script that periodically pulls the latest rules, validates them, and reports the result. Below is a production‑ready script and instructions for automating it.

### The Sync Script (`wrd-sync.sh`)

Place this script on every Wazuh node.  
**Where to run**: These commands must be executed **inside the Wazuh container** (or on the host if the Wazuh manager is installed natively).

First, create the script file inside the container:

```bash
docker exec -it multi-node-wazuh.worker-1 bash -c "cat > /usr/local/bin/wrd-sync.sh << 'EOF'"
#!/bin/bash
# wrd-sync.sh – Pull rules from WRD API, validate, restart, report status

NODE_ID="worker-01"                         # Must match the node_id in the API
API_KEY="node_cluster_worker-01_xxxxxxxx"   # The node's API key (from cluster registration)
API_URL="https://172.17.0.1:8443"           # Use host IP when container uses bridge network
RULES_DIR="/var/ossec/etc/rules"
LOG_FILE="/var/log/wrd-sync.log"

echo "$(date) - Starting sync on ${NODE_ID}" >> "$LOG_FILE"

# 1. Download the rules ZIP
curl -k -s -o /tmp/rules.zip \
  -H "Authorization: Bearer ${API_KEY}" \
  "${API_URL}/api/v1/nodes/${NODE_ID}/rules" >> "$LOG_FILE" 2>&1

# 2. Backup current rules and extract new ones
BACKUP_DIR="/var/ossec/backup/rules-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r "$RULES_DIR"/* "$BACKUP_DIR/" 2>/dev/null || true
unzip -o /tmp/rules.zip -d /var/ossec/etc/ >> "$LOG_FILE" 2>&1

# 3. Validate syntax
/var/ossec/bin/wazuh-analysisd -t >> "$LOG_FILE" 2>&1
SYNTAX_EXIT=$?

if [ $SYNTAX_EXIT -eq 0 ]; then
    echo "$(date) - Syntax OK, restarting wazuh-manager" >> "$LOG_FILE"
    /var/ossec/bin/wazuh-control restart >> "$LOG_FILE" 2>&1
    SYNC_STATUS="success"
else
    echo "$(date) - Syntax check failed, restoring backup" >> "$LOG_FILE"
    cp -r "$BACKUP_DIR"/* "$RULES_DIR/" 2>/dev/null || true
    SYNC_STATUS="failed"
fi

# 4. Report status back to API
curl -k -s -X POST "${API_URL}/api/v1/nodes/${NODE_ID}/status" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"status\":\"${SYNC_STATUS}\", \"deployed_version\":\"$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')\"}" >> "$LOG_FILE" 2>&1

echo "$(date) - Sync finished with status ${SYNC_STATUS}" >> "$LOG_FILE"
EOF
```

Make it executable:

```bash
docker exec -it multi-node-wazuh.worker-1 bash -c "chmod +x /usr/local/bin/wrd-sync.sh"
```

### Automating with Cron

Add a cron job to run the script every 5 minutes.  
**Where to run**: Inside the Wazuh container.

#### Option A: Manual inside container (ephemeral)

```bash
docker exec -it multi-node-wazuh.worker-1 bash -c "apt-get update && apt-get install -y cron curl unzip"
docker exec -it multi-node-wazuh.worker-1 bash -c "echo '*/5 * * * * /usr/local/bin/wrd-sync.sh' | crontab -"
docker exec -it multi-node-wazuh.worker-1 bash -c "service cron start"
```

#### Option B: Custom Dockerfile (persistent – recommended for production)

Create a `Dockerfile` next to your Wazuh `docker-compose.yml`:

```dockerfile
FROM wazuh/wazuh-manager:4.7.2

USER root
RUN apt-get update && apt-get install -y cron curl unzip

COPY wrd-sync.sh /usr/local/bin/wrd-sync.sh
RUN chmod +x /usr/local/bin/wrd-sync.sh && \
    echo '*/5 * * * * /usr/local/bin/wrd-sync.sh' | crontab -

CMD service cron start && /init
```

Then in your `docker-compose.yml`, replace `image: wazuh/wazuh-manager:4.7.2` with `build: .`. Rebuild and restart.

### Network Note

- When the Wazuh container uses the default bridge network, the host is reachable at `172.17.0.1`. In the script above, `API_URL` is set to `https://172.17.0.1:8443`. Adjust if your host IP differs or if you use a custom network.
- For native (non‑containerized) Wazuh installations, use `https://<api-server-ip>:8443`.

### Handling Rule Validation Errors

If your rules contain references to non‑existent parent rules (`if_sid`), the syntax check will fail. The script above restores the previous rules and reports a failure. To resolve:

- Ensure that all referenced rule IDs exist in the default Wazuh ruleset or are included in your Git repository.
- Use `wazuh-analysisd -t` locally to debug syntax issues before pushing to Git.

---

## API Reference

The full OpenAPI specification is available at `/docs` when the API is running. Below is a summary of the main endpoints.

### Health & Readiness

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (checks DB & Git repo) |

### Clusters

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/clusters` | Register a new cluster |
| GET | `/api/v1/clusters` | List all clusters |
| GET | `/api/v1/clusters/{cluster_id}` | Get cluster details |
| DELETE | `/api/v1/clusters/{cluster_id}` | Soft‑delete a cluster |
| POST | `/api/v1/clusters/{cluster_id}/sync` | Trigger rule sync |

### Nodes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/nodes/{node_id}/rules` | Download rules ZIP (used by nodes) |
| POST | `/api/v1/nodes/{node_id}/status` | Report sync status (used by nodes) |
| DELETE | `/api/v1/nodes/{node_id}` | Deregister a node |

### Rules

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/rules` | List current ruleset info |
| POST | `/api/v1/rules/sync-git` | Manually pull from Git |
| POST | `/api/v1/rules/validate` | Validate XML syntax of all rules |

### Authentication

All endpoints except health checks require an `Authorization: Bearer <api_key>` header. API keys are either **admin keys** (full access) or **node keys** (limited to reporting status and downloading rules). Node keys are tied to a specific node and are verified against the `cluster_nodes` table.

---

## Development

### Project Structure

```
.
├── alembic.ini                  # Alembic configuration
├── docker-compose.dev.yml        # Dev stack
├── Makefile                      # Common tasks
├── pyproject.toml                # Python dependencies & tool config
├── .env.example                  # Environment template
├── deployments/                  # Production Docker assets
│   └── docker/
│       ├── docker-compose.yml
│       └── Dockerfile
├── git-repo/                     # Local copy of rules Git repo (mounted volume)
├── migrations/                    # Alembic migration scripts
├── nginx/                         # NGINX config for production
├── scripts/                       # Utility scripts (init, backup, keygen)
└── src/                           # Application source code
    ├── api/                       # FastAPI route handlers
    ├── core/                       # Security, config
    ├── db/                          # Database models & session
    ├── models/                      # Pydantic schemas
    ├── services/                    # Business logic
    └── utils/                       # Git ops, validators
```

### Running Tests

**Where to run**: On your host machine (uses `docker exec` to run tests inside the API container).

```bash
make test          # all tests
make test-unit     # unit tests only
make test-integration  # integration tests
```

### Linting & Formatting

```bash
make lint          # check code style
make format        # auto‑format with black and ruff
```

### Creating Database Migrations

After changing models, generate a new Alembic revision:

```bash
make migrate-create m="description of change"
```

Then apply it:

```bash
make migrate
```

---

## Makefile Targets

| Target | Description | Where to run |
|--------|-------------|--------------|
| `up-dev` | Start development stack (hot‑reload) | Host |
| `up-prod` | Start production stack (3 replicas + NGINX) | Host |
| `down` | Stop all containers | Host |
| `logs` | Tail API logs (dev) | Host |
| `shell` | Open a shell in the API container (dev) | Host |
| `migrate` | Run database migrations | Host |
| `migrate-create` | Create a new Alembic revision | Host |
| `init-admin` | Create the first admin API key | Host |
| `show-admin-key` | Display the current admin key | Host |
| `test` | Run all tests | Host |
| `lint` | Run linters (black, ruff, mypy) | Host |
| `format` | Auto‑format code | Host |
| `secrets` | Generate secrets (idempotent) | Host |
| `env` | Copy `.env.example` to `.env` if missing | Host |
| `clean` | Remove containers, volumes, and pycache | Host |
| `backup` | Backup database and git‑repo | Host |

---

## Troubleshooting & FAQs

### Duplicate node entries in the database

If you re‑register a node with the same `node_id`, the API currently inserts a new row instead of updating the existing one. To clean up duplicates, run this **inside the PostgreSQL container** or via `docker exec` from host:

```bash
docker exec -it wrd-postgres psql -U api -d wazuh_api -c "
-- Find duplicates
SELECT node_id, COUNT(*) FROM cluster_nodes GROUP BY node_id HAVING COUNT(*) > 1;

-- Delete all but the latest (adjust as needed)
DELETE FROM cluster_nodes WHERE node_id='worker-01' AND id NOT IN (
    SELECT id FROM cluster_nodes WHERE node_id='worker-01' ORDER BY updated_at DESC LIMIT 1
);"
```

### `{"detail":"Invalid API key"}` when a node reports status

Make sure you are using the **node API key** (starts with `node_...`), not the admin key. Also verify that the node is registered in the same cluster and that the API key in the database matches (hashed).

### Rules file missing after sync

The sync script only restarts Wazuh if the syntax check passes. Check `/var/log/wrd-sync.log` on the node for errors. Common issues:
- Missing `if_sid` references (see below).
- Duplicate rule IDs.

### Warnings about `if_sid` not found

```
WARNING: Signature ID '100100' was not found in the 'if_sid' option of rule '100600'
```

This means a rule references a parent rule ID that does not exist in the current ruleset. Either add the missing parent rule to your Git repository or remove the `<if_sid>` from the child rule.

### Rule ID is duplicated

If you see `WARNING: Rule ID '100001' is duplicated`, two rule files define the same ID. Rename your custom rule to an unused ID (above 100000 is safe for custom rules).

### Node status stuck on `pending`

The node’s status update may not be reaching the API. Check:
- Cron is running on the node (inside container: `ps aux | grep cron`).
- The `API_KEY` and `API_URL` in `wrd-sync.sh` are correct.
- Network connectivity between the node and the API (e.g., firewall, bridge IP). From inside the container, try `curl -k https://172.17.0.1:8443/health`.

### `wazuh-control: command not found`

Ensure you are using the correct path: `/var/ossec/bin/wazuh-control`. Some older installations may use `/var/ossec/bin/ossec-control`.

---

## Security Considerations

- **API keys** are hashed with bcrypt before storage; they are only shown once upon creation. Store them in a secure vault (e.g., HashiCorp Vault, AWS Secrets Manager).
- **Docker secrets** are used in production for sensitive environment variables (database password, JWT secret). These are mounted as files inside containers and never appear in environment variables.
- **Network isolation**: In production, the API and database run on an internal `backend` network; only NGINX is exposed to the host.
- **HTTPS**: The production stack includes NGINX with SSL termination. Replace the self‑signed certificates with proper ones.
- **JWT tokens** are used only for internal purposes; the primary authentication mechanism is API keys.

---

## License

MIT
