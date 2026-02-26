.PHONY: help up-dev up-prod down logs migrate shell test lint build clean secrets

# ── Defaults ─────────────────────────────────────────────────────────────────
PROJECT_NAME=wrd-api
COMPOSE_DEV=docker-compose.dev.yml
COMPOSE_PROD=deployments/docker/docker-compose.yml

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Development ───────────────────────────────────────────────────────────────
up-dev: ## Start development stack (hot-reload, single replica)
	@echo "🚀 Starting WRD API in development mode..."
	@$(MAKE) secrets
	docker compose -f $(COMPOSE_DEV) up --build -d
	@echo "✅ API running  → http://localhost:8000"
	@echo "📖 API docs     → http://localhost:8000/docs"
	@echo "🔍 Health check → http://localhost:8000/health"

down: ## Stop all containers
	docker compose -f $(COMPOSE_DEV) down --remove-orphans
	docker compose -f $(COMPOSE_PROD) down --remove-orphans 2>/dev/null || true

logs: ## Tail API logs (dev)
	docker compose -f $(COMPOSE_DEV) logs -f wazuh-api

shell: ## Open shell in API container (dev)
	docker compose -f $(COMPOSE_DEV) exec wazuh-api bash

# ── Production ────────────────────────────────────────────────────────────────
up-prod: ## Start production stack (3 replicas, NGINX)
	@echo "🏭 Starting WRD API in production mode..."
	@$(MAKE) secrets
	docker compose -f $(COMPOSE_PROD) up --build -d
	@echo "✅ API running via NGINX → http://localhost:80"

# ── Database ──────────────────────────────────────────────────────────────────
migrate: ## Run Alembic migrations (dev)
	docker compose -f $(COMPOSE_DEV) exec wazuh-api alembic upgrade head

migrate-create: ## Create new migration (usage: make migrate-create m="description")
	docker compose -f $(COMPOSE_DEV) exec wazuh-api alembic revision --autogenerate -m "$(m)"

migrate-history: ## Show migration history
	docker compose -f $(COMPOSE_DEV) exec wazuh-api alembic history

# ── Admin ─────────────────────────────────────────────────────────────────────
init-admin: ## Initialize DB and create first admin key
	docker compose -f $(COMPOSE_DEV) exec wazuh-api python scripts/init_multi_node.py --create-admin --non-interactive

show-admin-key: ## Display the current admin API key
	@docker compose -f $(COMPOSE_DEV) exec wazuh-api cat /data/admin_key.txt && echo ""

# ── Testing ───────────────────────────────────────────────────────────────────
test: ## Run all tests
	docker compose -f $(COMPOSE_DEV) exec wazuh-api pytest tests/ -v --cov=src --cov-report=term-missing

test-unit: ## Run unit tests only
	docker compose -f $(COMPOSE_DEV) exec wazuh-api pytest tests/unit/ -v

test-integration: ## Run integration tests only
	docker compose -f $(COMPOSE_DEV) exec wazuh-api pytest tests/integration/ -v

# ── Code Quality ─────────────────────────────────────────────────────────────
lint: ## Run linters (black + ruff + mypy)
	docker compose -f $(COMPOSE_DEV) exec wazuh-api black --check src/ scripts/
	docker compose -f $(COMPOSE_DEV) exec wazuh-api ruff check src/ scripts/
	docker compose -f $(COMPOSE_DEV) exec wazuh-api mypy src/

format: ## Auto-format code
	docker compose -f $(COMPOSE_DEV) exec wazuh-api black src/ scripts/
	docker compose -f $(COMPOSE_DEV) exec wazuh-api ruff check --fix src/ scripts/

# ── Build ─────────────────────────────────────────────────────────────────────
build: ## Build Docker images
	docker compose -f $(COMPOSE_DEV) build --no-cache

# ── Secrets ───────────────────────────────────────────────────────────────────
secrets: ## Generate secrets (idempotent)
	@mkdir -p secrets
	@[ -f secrets/secret_key.txt ] || openssl rand -hex 32 > secrets/secret_key.txt && echo "  ✔ secret_key.txt"
	@[ -f secrets/jwt_secret.txt ] || openssl rand -hex 32 > secrets/jwt_secret.txt && echo "  ✔ jwt_secret.txt"
	@[ -f secrets/db_password.txt ] || openssl rand -base64 24 > secrets/db_password.txt && echo "  ✔ db_password.txt"
	@mkdir -p data

env: ## Copy .env.example to .env (if not exists)
	@[ -f .env ] || cp .env.example .env && echo "  ✔ .env created from template"

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean: ## Remove containers, volumes, and temp files
	docker compose -f $(COMPOSE_DEV) down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true

# ── Backup ────────────────────────────────────────────────────────────────────
backup: ## Run database + git-repo backup
	bash scripts/backup.sh
