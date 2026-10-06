---
name: setup-dev-env
description: Get a developer's machine ready for this repo in one pass — check every required tool (git, Node 24 via fnm, pnpm 11.5.2, uv + Python 3.14, Bicep CLI, az, just/make; optional Docker, gh, ODBC Driver 18) with scripts/doctor.sh, install what is missing through the OS package manager (winget / brew / apt + official installers), re-check, and when an install fails (admin rights, PATH, execution policy, proxy) hand the developer exact, numbered manual steps instead of guessing. Run on a fresh machine before /init-project or make install.
---

# Set up the development environment

> **Scope gate:** Running this is the approval to **check** the machine (read-only) and to
> **propose** installs. Installing changes the developer's machine, so the install list is shown
> once, as a whole, and needs a **yes** before anything runs. Never: elevate privileges yourself
> (`sudo`, "Run as administrator"), change global shell profiles without showing the exact line
> first, install anything not on the list below, or touch `.env` files / secrets.

## What "ready" means (from the repo's own pins — do not restate them from memory)

| Tool                   | Required | Version           | Pinned in                                                                                                                                  |
| ---------------------- | -------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| git                    | yes      | any               | —                                                                                                                                          |
| Node (via **fnm**)     | yes      | 24.x              | `.nvmrc`                                                                                                                                   |
| pnpm                   | yes      | 11.5.2 (corepack) | root `package.json` → `packageManager`                                                                                                     |
| uv                     | yes      | ≥ 0.10            | `.github/workflows/ci.yml` (`uv==0.10.9`)                                                                                                  |
| Python (via uv)        | yes      | 3.14              | `apps/api/pyproject.toml` → `requires-python`                                                                                              |
| Bicep CLI (standalone) | yes      | ≥ 0.30            | `scripts/doctor.sh` (`BICEP_MIN`); `make infra-build`, the format hook and agents call `bicep` directly                                    |
| just **or** make       | yes      | any               | `justfile` / `Makefile` (just recommended on Windows)                                                                                      |
| Docker (Compose v2)    | optional | any               | only for `make up` / image builds                                                                                                          |
| gh                     | optional | any               | `/git-flow` opens PRs with it                                                                                                              |
| ODBC Driver 18         | optional | 18                | only to run the api locally against the dev Azure SQL database                                                                             |
| az                     | yes      | any               | developers: `az login`, `make infra-whatif`/`infra-deploy ENV=dev`, Key Vault reads, `az acr login`. Agents: every call prompts (ADR-0012) |

## Steps

### 1. Check (read-only)

Run `bash scripts/doctor.sh` (on Windows this is Git Bash — the shell Claude Code already
uses). It prints one line per tool with `OK` / `MISSING` / `OLD` / `WARN` and the install
command for the detected OS. Show the developer the table **as printed**, then one sentence:
"N required tools missing/old, M optional."

If everything required is `OK`: say so, point to `make install` (or `just install`) and stop.
Do not install optional tools unless the developer asks.

### 2. Propose the install list (one confirmation)

From the `MISSING`/`OLD` rows, build the list in this order (dependencies first) and show it as
commands the developer will see run:

| OS                              | Package manager        | Commands (in order)                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------- | ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| **Windows** (PowerShell)        | winget                 | `winget install --id Git.Git -e` · `winget install --id Schniz.fnm -e` · `fnm install 24; fnm use 24; fnm default 24` · `corepack enable; corepack prepare pnpm@11.5.2 --activate` · `winget install --id astral-sh.uv -e` · `uv python install 3.14` · `winget install --id Microsoft.Bicep -e` · `winget install --id Microsoft.AzureCLI -e` · `winget install --id Casey.Just -e` · optional: `GitHub.cli`, `Docker.DockerDesktop`, `Microsoft.msodbcsql.18` |
| **macOS**                       | Homebrew               | `brew install git fnm uv just gh` · `fnm install 24 && fnm use 24 && fnm default 24` · `corepack enable && corepack prepare pnpm@11.5.2 --activate` · `uv python install 3.14` · `brew tap azure/bicep && brew install bicep` · `brew install azure-cli` · optional: `brew install --cask docker`, `msodbcsql18` (see doctor hint)                                                                                                                              |
| **Linux / WSL** (Debian/Ubuntu) | apt + official scripts | `sudo apt-get install -y git` (the developer runs the `sudo` lines) · `curl -fsSL https://fnm.vercel.app/install                                                                                                                                                                                                                                                                                                                                                | bash`·`fnm install 24 && fnm use 24 && fnm default 24`·`corepack enable && corepack prepare pnpm@11.5.2 --activate`·`curl -LsSf https://astral.sh/uv/install.sh | sh`·`uv python install 3.14`· Bicep: the release binary (doctor hint) · `curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash` ·`just` via apt/binary |

Winget ids above are verified against the winget catalogue; if `winget` reports
"No package found", the developer's winget source is stale — `winget source update` first.

Ask: **"Install these now? (yes / pick which / no — I'll do it manually)"**. Do not run
anything before the answer.

### 3. Install, one tool at a time

- Run each command separately, capture its output, and **stop at the first failure** — go to
  step 5 for that tool, then continue with the rest only if the failed tool is not a
  dependency of what follows (Node → pnpm; uv → Python).
- Windows: run winget from PowerShell (`powershell -NoProfile -Command "winget install ..."`)
  so its prompts and exit codes are visible. Never pass `--silent` with elevation tricks.
- Lines containing `sudo` are **never run by the agent** — print them for the developer to run
  in their own terminal and wait.
- After Node is installed, pnpm comes from **corepack** (Node 24 ships it). If `corepack` is
  not found, fall back to `npm i -g pnpm@11.5.2` and say why.

### 4. Re-check

If any question from steps 1–3 went unanswered (the install list, the `~/.bashrc` line), **ask it
again here** — never default silently and never skip it.

Run `bash scripts/doctor.sh` again. Anything still not `OK` that was just installed is almost
always a **PATH problem in this shell**, not a failed install — say that plainly and give the
"open a new terminal" instruction for the developer's shell (PowerShell / Git Bash / zsh /
bash). Then the final message:

```
## Environment — <date>
- Ready: <tools>
- Installed now: <tools>
- Still to do (you): <numbered manual steps, or "nothing">
Next: open a NEW terminal, run `bash scripts/doctor.sh` once more, then `make install` (or `just install`).
```

### 5. When something fails — the playbook (give exact, numbered steps)

Match the error to a row and print the steps verbatim, adapted to the tool. Do not retry the
same command more than twice.

| Symptom                                                                                                                                           | Cause                                                                                                                              | Steps for the developer                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| winget: `Installer failed with exit code: 1603` / `Access is denied` / UAC prompt dismissed                                                       | Installer needs admin (ODBC, Docker, sometimes Git/Bicep)                                                                          | 1. Press **Start**, type **PowerShell**, right-click → **Run as administrator**. 2. Paste the exact `winget install …` line shown above. 3. Accept the UAC prompt. 4. Close that window, open a **normal** terminal, run `bash scripts/doctor.sh`.                                                                                                                                                                                                                                                                                                                                                                                              |
| winget: `'winget' is not recognized` / `No package found matching input criteria`                                                                 | App Installer missing or stale source                                                                                              | 1. Open **Microsoft Store**, search **App Installer**, click **Update/Install**. 2. In PowerShell: `winget source update`. 3. Retry the command. If winget is blocked by policy, use the vendor's installer: fnm → GitHub releases, uv → `irm https://astral.sh/uv/install.ps1 \| iex`, Bicep → `bicep-win-x64.exe` from github.com/Azure/bicep/releases renamed to `bicep.exe` in a folder on PATH.                                                                                                                                                                                                                                            |
| `node`/`fnm`/`uv`/`bicep`/`az` "not recognized" **right after** a successful install                                                              | PATH is only updated for new processes                                                                                             | 1. Close **every** terminal window (and VS Code, if you run commands there). 2. Open a new one. 3. `bash scripts/doctor.sh`. If still missing on Windows: **Start → "Edit environment variables for your account" → Path → New** → add the tool's folder (`%LOCALAPPDATA%\Microsoft\WinGet\Links`, `%USERPROFILE%\.local\bin` for uv, `%LOCALAPPDATA%\fnm` for fnm), OK, new terminal.                                                                                                                                                                                                                                                          |
| `fnm` installed but `node` missing (`fnm env` never runs) — **most common on Windows:** PowerShell has `node`, the doctor (Git Bash) says MISSING | fnm needs one line in **each** shell's profile; Git Bash (used by `just`/`make`/Claude Code) does not read PowerShell's `$PROFILE` | Git Bash: 1. Create `~/.bashrc` (`C:\Users\<you>\.bashrc`) containing `eval "$(fnm env --shell bash)"` (no `--use-on-cd`: the cd hook fails in tool-spawned shells) — offer to write it, it is a one-line file in the developer's home, but **ask first**. 2. New terminal / restart VS Code. 3. `bash scripts/doctor.sh`. PowerShell (if `node` is missing there too): 1. `notepad $PROFILE` (create it if asked). 2. Add `fnm env --use-on-cd \| Out-String \| Invoke-Expression`. 3. Save, new terminal. No Node inside fnm yet: `fnm install 24; fnm default 24`. macOS/Linux: `eval "$(fnm env --use-on-cd)"` in `~/.zshrc` / `~/.bashrc`. |
| PowerShell: `… cannot be loaded because running scripts is disabled on this system`                                                               | Execution policy blocks `$PROFILE` / `corepack` shims                                                                              | 1. In a **normal** PowerShell: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. 2. Answer **Y**. 3. New terminal. (Current-user scope; no admin needed. If your organisation locks the policy, use Git Bash for this repo instead.)                                                                                                                                                                                                                                                                                                                                                                                                       |
| `corepack: command not found` / pnpm prepare fails with a signature/keyid error                                                                   | Old Node without corepack, or corepack's key store out of date                                                                     | 1. `node -v` must print `v24.x` — if not, fix Node first (`fnm use 24`). 2. `npm i -g corepack@latest` then `corepack enable && corepack prepare pnpm@11.5.2 --activate`. 3. Fallback that always works: `npm i -g pnpm@11.5.2`.                                                                                                                                                                                                                                                                                                                                                                                                                |
| `uv python install 3.14` fails / `pyodbc` build error on `uv sync`                                                                                | Download blocked, or no wheel for the interpreter                                                                                  | 1. Re-run `uv python install 3.14` (it resumes). 2. If your network blocks GitHub downloads, ask IT for `github.com` + `astral.sh` allow-listing or set `UV_PYTHON_INSTALL_MIRROR`. 3. `pyodbc` needs no compiler on 3.14 — a build error means the wrong Python was picked: `uv python pin 3.14` inside `apps/api`, then `uv sync` again.                                                                                                                                                                                                                                                                                                      |
| `SSL certificate problem` / `self-signed certificate in certificate chain` on any download                                                        | Corporate proxy / TLS inspection                                                                                                   | 1. Ask IT for the corporate root CA (`.crt`). 2. Windows: double-click → **Install certificate → Local Machine → Trusted Root**. 3. For Node: `setx NODE_EXTRA_CA_CERTS "C:\path\to\corp-ca.crt"`; for uv/pip: `setx SSL_CERT_FILE "C:\path\to\corp-ca.crt"`; for git: `git config --global http.sslCAInfo C:\path\to\corp-ca.crt`. 4. New terminal, retry. Never set `strict-ssl false` / `GIT_SSL_NO_VERIFY` as a fix.                                                                                                                                                                                                                        |
| Docker Desktop: `WSL 2 installation is incomplete` / needs reboot                                                                                 | WSL2 kernel missing                                                                                                                | 1. Admin PowerShell: `wsl --install`. 2. **Reboot.** 3. Start Docker Desktop, wait for "Engine running". 4. `docker info` in a normal terminal. Docker is optional — tests, `make dev` and mocks work without it.                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `bicep: command not found` after winget/brew success, or only `az bicep` works                                                                    | PATH (see above), or only the az-bundled copy is installed                                                                         | 1. `where.exe bicep` (Windows) / `which -a bicep`. 2. Install the standalone CLI (`winget install --id Microsoft.Bicep -e`); `az bicep` is not exposed as `bicep` on PATH. 3. `bicep --version` must print ≥ 0.30.                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ODBC: `Can't open lib 'ODBC Driver 18 for SQL Server'` when running the api locally                                                               | Driver not installed (tests never need it)                                                                                         | Windows: admin PowerShell → `winget install --id Microsoft.msodbcsql.18 -e`. macOS: the `brew tap microsoft/mssql-release …` line from the doctor hint (`HOMEBREW_ACCEPT_EULA=Y`). Linux: Microsoft's apt repo, same as `apps/api/Dockerfile` (`msodbcsql18` + `unixodbc`). Only needed to query the dev Azure SQL database from your machine.                                                                                                                                                                                                                                                                                                  |
| `just: command not found` on Windows and you'd rather not install it                                                                              | make is not on Windows either                                                                                                      | Install `just` (`winget install --id Casey.Just -e`) — the repo's `justfile` runs recipes in PowerShell natively. GNU make is for macOS/Linux/CI.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |

If none match: paste the full error, name the tool, and say which of the vendor pages to use
(fnm: github.com/Schniz/fnm · uv: docs.astral.sh/uv · Bicep: learn.microsoft.com "Install Bicep tools" · az: learn.microsoft.com "Install the Azure CLI"
· just: github.com/casey/just · Docker: docs.docker.com/desktop · ODBC: learn.microsoft.com "ODBC Driver 18 for SQL Server").
Do not invent flags or download URLs — `docs-lookup` if unsure.

## Never

- Run `sudo`, request elevation, or edit machine-wide settings (`Set-ExecutionPolicy` without
  `-Scope CurrentUser`, system PATH, `/etc/*`).
- Install a different major version than the pins to "make it work" — fix the pins in an
  approved change instead.
- Disable TLS verification anywhere to get past a proxy.
- Continue into `make install` / `/init-project` while a required tool is still `MISSING` —
  hand the manual steps over and stop.
