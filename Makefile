# =============================================================================
# Team Assistant — task runner (mirrors justfile, same targets).
# Requires: docker, pnpm (via corepack), uv, Node 24 (via .nvmrc / fnm).
# =============================================================================
.DEFAULT_GOAL := help
.PHONY: help doctor install dev test test-cov build up down logs clean fmt infra-build infra-whatif infra-deploy

# Target environment for the infra targets (dev | staging | prod). Only `dev` may be deployed locally.
ENV ?= dev
BICEP_PARAMS := infra/main.$(ENV).bicepparam
PLATFORM_RG = $$(node -p "require('./infra/platform/$(ENV).json').resourceGroup")

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

doctor: ## Check required tools + versions (git, Node 24, pnpm, uv, Python 3.14, Bicep, az, …); installs nothing
	bash scripts/doctor.sh

install: ## Install all dependencies (web, api)
	pnpm install
	pnpm -C apps/web install
	uv sync --directory apps/api

dev: ## Run both services locally (no Docker), concurrently
	pnpm install
	pnpm -C apps/web install
	pnpm run dev

test: ## Run all unit + integration tests (web, api)
	pnpm -C apps/web test
	uv run --directory apps/api pytest

test-cov: ## Run all tests with coverage (emits lcov.info + coverage.xml, as CI does)
	pnpm -C apps/web test:cov
	uv run --directory apps/api pytest --cov=app --cov-report=xml

build: ## Build all Docker images
	docker compose build

up: ## Build + start the full stack (docker compose up --build)
	docker compose up --build

down: ## Stop and remove containers
	docker compose down --remove-orphans

logs: ## Tail logs from all services
	docker compose logs -f

clean: ## Remove containers, volumes, and local build artifacts
	docker compose down -v --remove-orphans
	rm -rf apps/web/node_modules apps/web/.next
	rm -rf apps/api/.venv apps/api/__pycache__
	rm -rf node_modules

openapi: ## Export the api's OpenAPI contract + regenerate the web's TS types (run after any /v1 change)
	uv run --directory apps/api python -m app.openapi_export
	pnpm -C apps/web api-types
	pnpm exec prettier --write docs/reference/openapi.json apps/web/src/lib/api-types.ts

fmt: ## Format everything (prettier for JS/TS/JSON/MD, ruff for Python, bicep format)
	pnpm install
	pnpm run fmt
	for f in infra/*.bicep infra/modules/*.bicep; do bicep format "$$f"; done

# ── Infrastructure (Bicep, ADR-0012) — the USE-CASE tier only; the platform tier is the cloud team's. ──
infra-build: ## Compile + lint the use-case Bicep and the three param files (offline). Agents may run this.
	mkdir -p infra/.build
	bicep build infra/main.bicep --outfile infra/.build/main.json
	bicep lint infra/main.bicep
	for e in dev staging prod; do bicep build-params infra/main.$$e.bicepparam --outfile infra/.build/main.$$e.json; done

infra-whatif: ## Preview the deployment (ENV=dev|staging|prod). Needs `az login` + rights on the environment's resource group.
	az deployment group what-if --resource-group $(PLATFORM_RG) --template-file infra/main.bicep --parameters $(BICEP_PARAMS)

infra-deploy: ## Deploy locally — HUMANS ONLY, and ONLY ENV=dev (staging/prod deploy from GitHub)
	@if [ "$(ENV)" != "dev" ]; then echo "infra-deploy is local-dev only; staging/prod are deployed by .github/workflows/infra.yml"; exit 1; fi
	az deployment group create --resource-group $(PLATFORM_RG) --template-file infra/main.bicep --parameters $(BICEP_PARAMS)
