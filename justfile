# =============================================================================
# AI Accelerator — task runner (mirrors Makefile, same targets).
#   Local dev:   just install  |  just dev
#   Docker:      just build    |  just up   |  just down   |  just logs
#   Infra:       just infra-build  |  just infra-whatif dev  |  just infra-deploy dev (humans, dev only)
#
# Cross-platform shells: on Windows, recipes run in PowerShell (a POSIX
# `sh`/`bash` is often absent, and bare `bash` may resolve to an unconfigured
# WSL). On macOS/Linux they run in the default POSIX shell.
#
# Requires on PATH: pnpm (via corepack), uv, Node 24 (via .nvmrc / fnm), Docker.
# =============================================================================

set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# Show available targets
default:
    @just --list

# Check required tools + versions (git, Node 24, pnpm, uv, Python 3.14, Bicep, az, …); installs nothing
[unix]
doctor:
    bash scripts/doctor.sh

# Check required tools + versions (git, Node 24, pnpm, uv, Python 3.14, Bicep, az, …); installs nothing — via Git's bash.exe on Windows
[windows]
doctor:
    $gitBash = Join-Path $env:ProgramFiles 'Git\bin\bash.exe'; if (Test-Path $gitBash) { & $gitBash scripts/doctor.sh } else { Write-Host 'Git for Windows not found — install it (winget install --id Git.Git -e) or run: bash scripts/doctor.sh from Git Bash' }

# Install all dependencies (web, api)
install:
    pnpm install
    pnpm -C apps/web install
    uv sync --directory apps/api

# Run both services locally (no Docker), concurrently
dev:
    pnpm install
    pnpm -C apps/web install
    pnpm run dev

# Run all unit + integration tests (web, api)
test:
    pnpm -C apps/web test
    uv run --directory apps/api pytest

# Run all tests with coverage (emits lcov.info + coverage.xml, as CI does)
test-cov:
    pnpm -C apps/web test:cov
    uv run --directory apps/api pytest --cov=app --cov-report=xml

# Build all Docker images
build:
    docker compose build

# Build + start the full stack (docker compose up --build)
up:
    docker compose up --build

# Stop and remove containers
down:
    docker compose down --remove-orphans

# Tail logs from all services
logs:
    docker compose logs -f

# Export the api's OpenAPI contract + regenerate the web's TS types (run after any /v1 change)
openapi:
    uv run --directory apps/api python -m app.openapi_export
    pnpm -C apps/web api-types
    pnpm exec prettier --write docs/reference/openapi.json apps/web/src/lib/api-types.ts

# Format everything (prettier for JS/TS/JSON/MD, ruff for Python, bicep format)
fmt:
    pnpm install
    pnpm run fmt
    bicep format infra/main.bicep

# ── Infrastructure (Bicep, ADR-0012) — the USE-CASE tier only; the platform tier is the cloud team's. ──

# Compile + lint the use-case Bicep and the three param files (offline). Agents may run this.
infra-build:
    bicep build infra/main.bicep --outfile infra/.build/main.json
    bicep lint infra/main.bicep
    bicep build-params infra/main.dev.bicepparam --outfile infra/.build/main.dev.json
    bicep build-params infra/main.staging.bicepparam --outfile infra/.build/main.staging.json
    bicep build-params infra/main.prod.bicepparam --outfile infra/.build/main.prod.json

# Preview the deployment for one environment. Needs `az login` + rights on that environment's resource group.
infra-whatif env="dev":
    az deployment group what-if --resource-group "$(node -p "require('./infra/platform/{{env}}.json').resourceGroup")" --template-file infra/main.bicep --parameters infra/main.{{env}}.bicepparam

# Deploy locally — HUMANS ONLY, and ONLY dev (staging/prod deploy from .github/workflows/infra.yml)
infra-deploy env="dev":
    @{{ if env == "dev" { "az deployment group create --resource-group \"$(node -p \"require('./infra/platform/dev.json').resourceGroup\")\" --template-file infra/main.bicep --parameters infra/main.dev.bicepparam" } else { "echo 'infra-deploy is local-dev only; staging/prod are deployed by .github/workflows/infra.yml' && exit 1" } }}

# Remove containers, volumes, and local build artifacts (macOS / Linux)
[unix]
clean:
    -docker compose down -v --remove-orphans
    rm -rf apps/web/node_modules apps/web/.next apps/api/.venv apps/api/__pycache__ node_modules

# Remove containers, volumes, and local build artifacts (Windows / PowerShell)
[windows]
clean:
    -docker compose down -v --remove-orphans
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue apps/web/node_modules, apps/web/.next, apps/api/.venv, apps/api/__pycache__, node_modules
