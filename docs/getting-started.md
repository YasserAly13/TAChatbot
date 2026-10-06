# Getting started

Onboarding guide for a developer joining an AI project built on the **AI Accelerator** (the
Diriyah Company AI team's starter template, built by Orion Digital Solutions). It takes you
from a fresh clone to a running two-service stack with a verified `trace_id` flowing end to
end, and points at the deeper documentation once you are productive.

**Audience:** any developer who will write code in this repo — front-end, back-end, or both.
No prior knowledge of the template is assumed; familiarity with Node, Docker, and Python
tooling is.

**What you will have at the end:**

- both services running (via Docker or locally), reachable at `:3000` / `:8000`;
- a verified `web → api` request carrying one `x-trace-id` across the hop;
- an understanding of why `"observability": "disabled"` is the correct local state;
- the test suites running green;
- a map of where to go next.

Everything below documents the template's **foundation** — the wired-together services,
tracing, and observability. There are no business features and no auth yet; see
[_Scope & delivery status_](../README.md#scope--delivery-status) in the root README.

---

## Prerequisites

| Tool            | Version                | Notes                                                                                                  |
| --------------- | ---------------------- | ------------------------------------------------------------------------------------------------------ |
| **Docker**      | with Compose v2        | Required for Path A. `docker compose`, not `docker-compose`.                                           |
| **Node**        | 24                     | Pinned in [`.nvmrc`](../.nvmrc), Dockerfiles, and every `engines` field.                               |
| **pnpm**        | 11.5.2                 | Enable with `corepack enable` — do not install it globally with npm.                                   |
| **Python**      | 3.14                   | Only for `apps/api`.                                                                                   |
| **uv**          | ≥ 0.10                 | Manages the Python venv and lockfile. CI pins `uv==0.10.9`.                                            |
| **Task runner** | `just` _or_ GNU `make` | Same target names in both — [`justfile`](../justfile) / [`Makefile`](../Makefile).                     |
| **Bicep CLI**   | ≥ 0.30                 | Standalone `bicep` (not `az bicep`) — what `make infra-build`, the format hook and agents call.        |
| **az**          | any                    | `az login`; `make infra-whatif`/`infra-deploy ENV=dev`, Key Vault reads. Agents are prompted per call. |

### Windows notes

- **Prefer [`just`](https://github.com/casey/just).** The `justfile` sets
  `windows-shell := ["powershell.exe", …]`, so recipes run natively in PowerShell. The
  `Makefile` assumes a POSIX shell and is what CI and macOS/Linux use.
- **`just clean` is OS-aware** — the `justfile` has separate `[unix]` and `[windows]`
  recipes, so cleanup works on both.
- **Get everything on `PATH` before you start.** `node` and `pnpm` (typically via
  [`fnm`](https://github.com/Schniz/fnm)), `uv`, and `docker` must all resolve in the shell
  that runs `just dev`. If `fnm` is only initialised in your interactive profile, a recipe
  spawned by `just` may not see Node — verify with `node -v`, `pnpm -v`, `uv --version`, and
  `docker version` in the same shell first.

### Version check

```bash
bash scripts/doctor.sh     # or: make doctor / just doctor
```

One line per tool — `OK`, `MISSING`, `OLD` or `WARN` (optional / not on PATH in this shell) —
with the install command for your OS next to anything that is not ready. It installs nothing
and exits non-zero while a required tool is missing. Required: git, Node 24, pnpm 11.5.2, uv,
Python 3.14, Bicep CLI ≥ 0.30, `az`, `just` or `make`. Optional: Docker, `gh`, ODBC Driver 18 (only
to query the dev Azure SQL database from your machine).

### Installing the tools

**With Claude Code:** `/setup-dev-env`. It runs the doctor, shows you the install list for your
OS, waits for your **yes**, installs one tool at a time, re-checks, and — when something needs
admin rights, a new terminal, a profile line or IT (proxy certificates) — gives you numbered
steps instead of retrying blindly. It never runs `sudo`, never elevates, never disables TLS.

**By hand** (same commands the skill uses; open a **new terminal** after installing):

| Tool               | Windows (PowerShell, winget)                                                                                                                                                                                                           | macOS (Homebrew)                                                                        | Linux / WSL (Debian/Ubuntu)                                               |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| git                | `winget install --id Git.Git -e`                                                                                                                                                                                                       | `xcode-select --install`                                                                | `sudo apt-get install -y git`                                             |
| fnm (Node manager) | `winget install --id Schniz.fnm -e`, then add to `$PROFILE`: `fnm env --use-on-cd \| Out-String \| Invoke-Expression` **and** to `~/.bashrc` (Git Bash — what `just`, `make` and Claude Code run in): `eval "$(fnm env --shell bash)"` | `brew install fnm`, then `eval "$(fnm env --use-on-cd)"` in `~/.zshrc`                  | `curl -fsSL https://fnm.vercel.app/install \| bash`                       |
| Node 24            | `fnm install 24; fnm use 24; fnm default 24`                                                                                                                                                                                           | same                                                                                    | same                                                                      |
| pnpm 11.5.2        | `corepack enable; corepack prepare pnpm@11.5.2 --activate`                                                                                                                                                                             | same                                                                                    | same (fallback anywhere: `npm i -g pnpm@11.5.2`)                          |
| uv                 | `winget install --id astral-sh.uv -e`                                                                                                                                                                                                  | `brew install uv`                                                                       | `curl -LsSf https://astral.sh/uv/install.sh \| sh`                        |
| Python 3.14        | `uv python install 3.14`                                                                                                                                                                                                               | same                                                                                    | same                                                                      |
| Bicep CLI ≥ 0.30   | `winget install --id Microsoft.Bicep -e`                                                                                                                                                                                               | `brew tap azure/bicep && brew install bicep`                                            | release binary — see the doctor hint                                      |
| just               | `winget install --id Casey.Just -e`                                                                                                                                                                                                    | `brew install just`                                                                     | `sudo apt-get install -y just` (or the GitHub release binary)             |
| Docker (optional)  | `winget install --id Docker.DockerDesktop -e` (needs WSL2 + reboot)                                                                                                                                                                    | `brew install --cask docker`                                                            | docs.docker.com/engine/install                                            |
| gh (optional)      | `winget install --id GitHub.cli -e`                                                                                                                                                                                                    | `brew install gh`                                                                       | github.com/cli/cli — install_linux.md                                     |
| ODBC 18 (optional) | `winget install --id Microsoft.msodbcsql.18 -e` (admin)                                                                                                                                                                                | `brew tap microsoft/mssql-release … && HOMEBREW_ACCEPT_EULA=Y brew install msodbcsql18` | Microsoft apt repo (`msodbcsql18 unixodbc`) — as in `apps/api/Dockerfile` |
| az (optional)      | `winget install --id Microsoft.AzureCLI -e`                                                                                                                                                                                            | `brew install azure-cli`                                                                | `curl -sL https://aka.ms/InstallAzureCLIDeb \| sudo bash`                 |

**When it fails** — the four usual causes, in order of likelihood:

1. **PowerShell has `node` but the doctor says `node` MISSING** → the doctor runs in Git Bash,
   which never reads PowerShell's `$PROFILE`. Create `C:\Users\<you>\.bashrc` with the single
   line `eval "$(fnm env --shell bash)"`, open a new terminal (or restart VS Code),
   run the doctor again. (`/setup-dev-env` offers to write that file for you.)
2. **"not recognized" right after a successful install** → the PATH only refreshes for new
   processes. Close every terminal (and VS Code, if you run commands there), open a new one,
   run the doctor again.
3. **Installer needs admin** (ODBC, Docker, sometimes Bicep; error `1603` / "Access is denied") →
   Start → type _PowerShell_ → right-click → **Run as administrator** → paste the same command
   → accept the prompt → back to a normal terminal.
4. **PowerShell refuses to load `$PROFILE`** ("running scripts is disabled") →
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, answer **Y**, new terminal.

Corporate proxy / certificate errors, corepack signature errors, WSL2 for Docker and the
other cases are in the skill's playbook
([`.claude/skills/setup-dev-env/SKILL.md`](../.claude/skills/setup-dev-env/SKILL.md) → _When
something fails_).

---

## Using this template

If you are **starting a new AI project** from the template, rename it once, immediately
after cloning, before writing any feature code. Every project-identity string is a placeholder
from one of four families (`AI Accelerator`, `ai-accelerator`, `@ai-accelerator/*`,
`ai-accelerator-api`), and the repo ships a `/rename-project` command that replaces them all
in one pass and regenerates `apps/api/uv.lock`.

Full instructions and the placeholder table: [_Using this template_](../README.md#using-this-template).

If you are **joining a project that has already been renamed**, skip this — the names you see
are your project's names, and this guide's `ai-accelerator` references map onto them.

---

## Environment setup

Copy every `.env.example` to its `.env` counterpart. Nothing is secret in the defaults; the
files are commented placeholders.

```bash
cp .env.example .env                        # root — consumed by docker-compose substitution
cp apps/web/.env.example apps/web/.env.local # local (non-Docker) runs
cp apps/api/.env.example apps/api/.env
```

PowerShell:

```powershell
Copy-Item .env.example .env
Copy-Item apps/web/.env.example apps/web/.env.local
Copy-Item apps/api/.env.example apps/api/.env
```

Four things to internalise:

1. **Root vs. per-app.** The root [`.env`](../.env.example) is read by `docker-compose` for
   `${VAR}` substitution. The per-app files are for local (non-Docker) runs — `web` loads its
   own natively through Next, and the `api` loads `apps/api/.env` itself on startup
   (`load_local_env()` in `app/main.py`) — the file is optional.
   (`apps/web/.env.example` names `.env.local` as its target; Next also reads a plain `.env`,
   so either works for `web` — pick one and stay consistent.)
2. **Ambient env always wins.** A value already exported in your shell (or injected by
   Compose / Container Apps) is never overwritten by a `.env` file.
3. **Containers never ship `.env` files.** Every `.dockerignore` excludes `.env` / `.env.*`,
   so a container's configuration comes only from its environment.
4. **Leaving `APPLICATIONINSIGHTS_CONNECTION_STRING` empty is correct locally.** That is
   _degraded mode_, not a failure — see [Verifying your setup](#verifying-your-setup).

The full variable reference lives in
[`docs/reference/environment-variables.md`](reference/environment-variables.md); the root
README's [_Environment variables_](../README.md#environment-variables) table is the short form.

---

## Path A — Docker (recommended first run)

```bash
cp .env.example .env
make up          # or: just up   — or: docker compose up --build
```

This builds both images and starts them on one bridge network. Each service declares a
`/health` healthcheck, and `web` has `depends_on: api: condition: service_healthy`, so
Compose starts `api` → `web` in order and does not expose the UI until the backend behind it
is actually ready. The first click therefore works — no race.

Then open **<http://localhost:3000>**.

The page has **two button rows**:

- **Ping** (liveness) — `/api/ping-backend` → api `/ping`
- **Info** (health · version · runtime) — `/api/info-backend` → api `/info`

Every button calls a **same-origin** Next.js route handler (the BFF); the BFF calls the `api`
server-side. The rendered response includes the `trace_id` — note that the id the api reports
is the one `web` minted (`0eb0…`), carried unchanged across the hop.

Other Docker targets:

```bash
make build   # build all images          (docker compose build)
make up      # build + start the stack   (docker compose up --build)
make down    # stop + remove containers
make logs    # tail logs from all services
make clean   # down -v + remove local build artifacts
```

Inside the Compose network, `web` addresses the backend by DNS name (`http://api:8000`);
the browser only ever sees `localhost:3000`.

---

## Path B — local, no Docker

```bash
make install   # root tooling + pnpm install (web) + uv sync (api)
make dev       # both concurrently
```

`make dev` (equivalently `just dev`, or `pnpm run dev` once installed) runs the root
`concurrently` script, which starts:

| Service | Command                                                     | URL                     |
| ------- | ----------------------------------------------------------- | ----------------------- |
| `web`   | `pnpm -C apps/web dev` → `next dev -p 3000`                 | <http://localhost:3000> |
| `api`   | `uv run --directory apps/api uvicorn app.main:app --reload` | <http://localhost:8000> |

Output is prefixed and colour-coded per service (`web` green, `api` magenta); `Ctrl-C`
kills both (`concurrently -k`).

> **`pnpm -C apps/<app>`, never `pnpm --filter`.** The apps are **independent packages** with
> their own lockfiles and Dockerfiles — there is no pnpm workspace and no Turborepo, so
> workspace filters do not resolve. See [`.claude/rules/00-architecture.md`](../.claude/rules/00-architecture.md).

Individual services, when you only need one:

```bash
pnpm -C apps/web dev
uv run --directory apps/api uvicorn app.main:app --reload --port 8000
```

---

## Verifying your setup

Hit each service's `/health` endpoint directly. They are **unversioned** — `/ping`, `/info`,
and `/health` are the only endpoints exempt from the mandatory `/v1` prefix, because container
and Azure health probes target fixed paths.

```bash
curl http://localhost:3000/health   # web
curl http://localhost:8000/health   # api
```

Expected shape (values differ per service):

```json
{
  "status": "ok",
  "service": "api",
  "trace_id": "0c700f8e2c9a7b4d16035e9c2a8f4712",
  "observability": "disabled",
  "reason": "no Azure connection string"
}
```

### `"observability": "disabled"` is normal here

The template is **fail-safe by design**. With no `APPLICATIONINSIGHTS_CONNECTION_STRING`,
each service skips remote export, prints a startup warning
(`Observability disabled: no Azure connection string — running with local stdout logging
only`), and reports `disabled` on `/health` — it does **not** crash and does **not** lose
logging. Structured JSON logs still go to stdout, and the `trace_id` is still generated,
propagated, and echoed. That is the expected local state; set a real connection string only
when you want telemetry in Azure Monitor.

If you _did_ set a connection string and still see `disabled`, the `reason` field names the
cause — see [`docs/operations/runbooks/observability-degraded.md`](operations/runbooks/observability-degraded.md).

### Verify the trace contract

Check that a valid inbound id is adopted unchanged, and that an absent one is minted with the
receiving service's origin (`web=0eb0`, `api=0c70`):

```bash
# adopt: the response echoes exactly what you sent
curl -i -H "x-trace-id: 0eb00aaaaaaaaaaaaaaaaaaaaaaaaaaa" http://localhost:8000/ping

# generate: no inbound header -> a fresh 0c70… id, echoed on the response
curl -i http://localhost:8000/ping
```

Then exercise the hop through the BFF and confirm one id spans it:

```bash
curl -si http://localhost:3000/api/ping-backend
# browser -> web BFF -> api /ping
# the trace_id in the api's body and the x-trace-id response header are the same 0eb0… id
# (web is the origin; the api adopted it)
```

The id is `origin(4 hex) + env(1 hex) + random(27 hex)` = 32 hex, matching
`^[0-9a-f]{32}$`. Full schema: [_`trace_id` — the invariant_](../README.md#trace_id--the-invariant).

---

## Running the tests

```bash
make test        # everything, fast
make test-cov    # everything with coverage, the way CI runs it
```

Per service:

```bash
pnpm -C apps/web test                      # Vitest (node env)
uv run --directory apps/api pytest      # pytest + Starlette TestClient
```

All suites run **offline** — no database, no Azure, no network; outbound calls are mocked. If
a test tries to reach something real, that is a bug in the test. The Playwright e2e suite is
**manual/local only** and needs the full stack up; it is deliberately not part of CI.

Details, conventions, and what every suite must assert: [Testing guide](development/testing.md).

---

## Troubleshooting

### `components.ComponentMod.handler is not a function` (web)

You ran a local production `pnpm -C apps/web build` and then `next dev` against the same
`.next` directory, mixing production and development artifacts.

**Fix:** delete `apps/web/.next` and restart the dev server. Docker builds are isolated, so
`just build` / `just up` never collide with `just dev`.

### `uv sync --frozen` fails after renaming the project

`apps/api/uv.lock` records the project's own package name, so renaming
`ai-accelerator-api` in `pyproject.toml` invalidates it and the Docker build (which uses
`--frozen`) fails.

**Fix:** run `uv lock` in `apps/api`, then rebuild. `/rename-project` does this
automatically; a manual rename does not.

### `pnpm install --frozen-lockfile` fails in a Docker build

`apps/web` has its own `pnpm-workspace.yaml` carrying pnpm 11's build-script settings. The
Dockerfile must `COPY` that file into the deps stage alongside
`package.json` and the lockfile, or the install behaves differently than it does locally. If
you edit a Dockerfile, keep that COPY.

### Port already in use (3000 / 8000)

Something else holds the port — often a previous `make dev` that did not exit cleanly, or a
still-running Compose stack.

```bash
make down                        # if it is the Docker stack
netstat -ano | findstr :3000     # Windows: find the PID, then Stop-Process -Id <pid>
lsof -i :3000                    # macOS / Linux
```

The ports are part of the shared contract (`web=3000`, `api=8000`) — the
health probes, Compose DNS, and `.env.example` defaults all assume them. Prefer freeing the
port over changing it.

### `pnpm: command not found` / wrong Node version (Windows)

`corepack enable` provisions pnpm from the active Node install, so it only exists for the Node
version `fnm` currently has selected. Run `fnm use` (the repo pins `24` in `.nvmrc`), then
`corepack enable`, and confirm `node -v` / `pnpm -v` in the _same_ shell you will run `just`
from.

### `pnpm --filter` does nothing

There is no pnpm workspace. Use `pnpm -C apps/<app> <script>`.

### Python OpenTelemetry version conflicts

`azure-monitor-opentelemetry==1.8.8` hard-pins `opentelemetry-sdk==1.40`,
`opentelemetry-api==1.40.0`, and every instrumentation package to `==0.61b0`. Do not bump the
instrumentation pins independently — let the Azure distro drive them.

### Database errors on boot

**There is no local database — ever.** Every database is an Azure SQL Database created by the
use-case Bicep deployment (`infra/main.bicep`); for real work get the **dev** database's URL from Key Vault (secret `DATABASE-URL`)
into `apps/api/.env`, and ask for your public IP to be added to the SQL firewall allowlist
(`developerIpAllowlist` in `infra/main.dev.bicepparam`). Until then `DATABASE_URL` ships as a
placeholder. The SQLAlchemy async engine is **lazy** — `create_async_engine` opens no connection
until the first query — so the `api` boots fine without a reachable database (the baseline issues
no queries). If you see a connection error, something in your code is querying — that is the
thing to look at, not the placeholder URL. Spelling traps: the scheme is `mssql+aioodbc://`, the
`driver=ODBC+Driver+18+for+SQL+Server` keyword is mandatory, and `Encrypt=yes` +
`TrustServerCertificate=no` stay on. Running the api **outside Docker** needs Microsoft ODBC
Driver 18 installed on your machine only when you actually query; tests never do. Background:
[_Database (SQLAlchemy 2 async + Alembic)_](../README.md#database-sqlalchemy-2-async--alembic).

### `alembic` prints nothing / only `BEGIN TRANSACTION;` … `COMMIT;`

Expected. `alembic/versions/` is empty, so `uv run --directory apps/api alembic heads` has
nothing to list and `alembic upgrade head --sql` has no SQL to render. Migrations are never run
by this platform; see [data.md](architecture/data.md) for how a project grows the model set.

---

## Where to go next

**Understand the system**

- [`docs/architecture/`](architecture/README.md) — the deep dive: system
  [overview](architecture/overview.md), the [`trace_id` contract](architecture/tracing.md),
  the [observability stack](architecture/observability.md), and the
  [data layer](architecture/data.md).
- [`README.md`](../README.md) — the quick reference: architecture at a glance, BFF flow,
  versioning, env vars.

**Start contributing**

- [Development guide](development/README.md) — [workflow & CI](development/workflow.md),
  [adding a feature](development/adding-a-feature.md), [testing](development/testing.md),
  [coding standards](development/coding-standards.md).
- [`docs/adr/`](adr/README.md) — the decisions behind the current shape, starting with
  [ADR-0001 (mandatory API versioning)](adr/0001-api-versioning.md); ADR-0003 and ADR-0004
  explain why there are two services and why the database lives in `apps/api`;
  [ADR-0005](adr/0005-name-services-by-role.md) explains why the FastAPI service is named `api`.

**Look things up**

- `docs/reference/` — [HTTP API](reference/http-api.md),
  [environment variables](reference/environment-variables.md),
  [commands](reference/commands.md).
- [`docs/operations/`](operations/README.md) — running it: the
  [KQL starter pack](operations/kql-starter-pack.md) and the
  [runbooks](operations/runbooks/README.md).
- [`docs/security/`](security/README.md) — the security posture and threat models.

> If a document disagrees with the code, **the code wins** — then fix the document, in the
> same change.
