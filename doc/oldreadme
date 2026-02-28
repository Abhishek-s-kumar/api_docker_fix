# Wazuh Rules Distribution API (WRD API) v2.0.0

> **Centralized GitOps-based rules management for distributed Wazuh clusters**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-red)](https://redis.io)
[![Docker](https://img.shields.io/badge/Docker-24.0+-blue)](https://docker.com)

## Overview

The WRD API centralizes Wazuh rule distribution across multi-node clusters. Instead of manually syncing
rules across each Wazuh manager, teams push rules to a Git repository and the WRD API handles atomic,
versioned distribution across all registered nodes — with rollback support.

## Quick Start

```bash
# 1. Clone & setup
git clone https://github.com/Abhishek-s-kumar/wazuh-api-docker.git wazuh-api-docker
cd wazuh-api-docker

# 2. Generate secrets + copy env
make secrets
make env

# 3. Start development stack
make up-dev

# 4. Initialize admin key
make init-admin

# 5. Display admin key
make show-admin-key
```

After `make up-dev`:
- **API**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health**: http://localhost:8000/health

## Architecture

```
Load Balancer (NGINX)
       │
   ┌───┴───┐
   API ×3  │  ← FastAPI + Uvicorn workers
   └───┬───┘
       │
  ┌────┼────┐
  │    │    │
 PG  Redis  Git
```

See [docs/architecture.md](docs/architecture.md) for full diagrams.

## API Reference

Full OpenAPI docs at `/docs` when running. See [docs/api-reference.md](docs/api-reference.md).

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| GET | `/ready` | Readiness check (DB + Redis) |
| POST | `/api/v1/clusters` | Register Wazuh cluster |
| GET | `/api/v1/clusters` | List all clusters |
| POST | `/api/v1/clusters/{id}/sync` | Trigger rule sync |
| GET | `/api/v1/nodes/{id}/rules` | Pull rules package |
| POST | `/api/v1/nodes/{id}/status` | Report sync status |
| GET | `/api/v1/rules` | List rulesets |
| POST | `/api/v1/rules/sync-git` | Manual git pull |

## Make Targets

```bash
make up-dev       # Start dev stack
make up-prod      # Start production stack
make down         # Stop all containers
make logs         # Tail API logs
make shell        # Shell into API container
make migrate      # Run DB migrations
make init-admin   # Initialize admin key
make test         # Run test suite
make lint         # Run linters
make backup       # Backup DB + rules
make clean        # Full cleanup
```

## Deployment

- **Docker Compose (dev)**: `make up-dev`
- **Docker Compose (prod)**: `make up-prod`
- **Kubernetes**: See [docs/deployment-guide.md](docs/deployment-guide.md)

## Security Notes

- API keys are stored as bcrypt hashes — keys are only shown once on creation
- All secrets are mounted via Docker Secrets (never in env vars in production)
- JWT tokens expire in 60 minutes by default
- All inter-service traffic uses internal Docker networks

## License

MIT
