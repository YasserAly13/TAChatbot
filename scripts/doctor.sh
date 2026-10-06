#!/usr/bin/env bash
# =============================================================================
# doctor.sh — checks that every tool this repo needs is installed, on PATH and
# at a supported version, and prints the install command for THIS machine's OS
# for anything missing. Read-only: installs nothing, changes nothing.
#
#   bash scripts/doctor.sh          # human-readable table, exit 1 if a required tool fails
#   bash scripts/doctor.sh --json   # one JSON object per line (what /setup-dev-env parses)
#
# Works in Git Bash (Windows), macOS and Linux. Versions come from the repo's own
# pins: .nvmrc (Node), package.json packageManager (pnpm), apps/api/pyproject.toml
# (Python); the Bicep CLI floor is set here. Keep them in sync.
# =============================================================================
set -u

NODE_MAJOR=24
PNPM_VERSION="11.5.2"
UV_MIN="0.10"
PYTHON_VERSION="3.14"
BICEP_MIN="0.30"

JSON=0
[ "${1:-}" = "--json" ] && JSON=1

# ---- OS detection ------------------------------------------------------------
case "$(uname -s 2>/dev/null)" in
  MINGW* | MSYS* | CYGWIN*) OS=windows ;;
  Darwin) OS=macos ;;
  Linux) OS=linux ;;
  *) OS=unknown ;;
esac
if [ "$OS" = "linux" ] && grep -qi microsoft /proc/version 2>/dev/null; then OS=wsl; fi

# ---- helpers -----------------------------------------------------------------
REQUIRED_FAILED=0
ROWS=()

# ver_ge A B — true when dotted version A >= B (numeric, up to 3 components)
ver_ge() {
  local a b i
  IFS=. read -r -a a <<<"${1//[!0-9.]/}"
  IFS=. read -r -a b <<<"${2//[!0-9.]/}"
  for i in 0 1 2; do
    local x=${a[$i]:-0} y=${b[$i]:-0}
    if ((10#$x > 10#$y)); then return 0; fi
    if ((10#$x < 10#$y)); then return 1; fi
  done
  return 0
}

first_version() { grep -oE '[0-9]+(\.[0-9]+)+' | head -1; }

# hint <windows> <macos> <linux>
hint() {
  case "$OS" in
    windows) printf '%s' "$1" ;;
    macos) printf '%s' "$2" ;;
    *) printf '%s' "$3" ;;
  esac
}

# row <tool> <status:ok|missing|old|warn> <required:1|0> <found> <want> <hint>
row() {
  local tool=$1 status=$2 required=$3 found=$4 want=$5 h=$6
  if [ "$required" = 1 ] && { [ "$status" = missing ] || [ "$status" = old ]; }; then
    REQUIRED_FAILED=1
  fi
  if [ $JSON = 1 ]; then
    printf '{"tool":"%s","status":"%s","required":%s,"found":"%s","want":"%s","hint":"%s"}\n' \
      "$tool" "$status" "$([ "$required" = 1 ] && echo true || echo false)" \
      "${found//\"/\\\"}" "${want//\"/\\\"}" "${h//\"/\\\"}"
  else
    local mark
    case "$status" in
      ok) mark="OK     " ;;
      missing) mark="MISSING" ;;
      old) mark="OLD    " ;;
      *) mark="WARN   " ;;
    esac
    local req=" "
    [ "$required" = 1 ] && req="*"
    printf '  %s %s %-12s found: %-28s want: %s\n' "$mark" "$req" "$tool" "$found" "$want"
    [ "$status" != ok ] && [ -n "$h" ] && printf '            -> %s\n' "$h"
  fi
}

# ---- checks ------------------------------------------------------------------
[ $JSON = 0 ] && printf 'Team Assistant doctor — OS: %s\n\n' "$OS"

# repo integrity — a copy made without hidden folders loses .github/ and .claude/ (seen in the first dry run)
REPO_MISSING=""
for req in .github/workflows/ci.yml .claude/settings.json .nvmrc scripts/doctor.sh infra/main.bicep infra/platform/dev.json; do
  [ -e "$req" ] || REPO_MISSING="$REPO_MISSING $req"
done
if [ -z "$REPO_MISSING" ]; then
  row repo ok 1 "complete" "all template folders present" ""
else
  row repo missing 1 "missing:$REPO_MISSING" "all template folders present" "the clone is incomplete (hidden folders lost in a copy?) — clone again with git instead of copying files; run this from the repo root"
fi

# git
if command -v git >/dev/null 2>&1; then
  row git ok 1 "$(git --version | first_version)" "any" ""
else
  row git missing 1 "-" "any" "$(hint 'winget install --id Git.Git -e' 'xcode-select --install  (or: brew install git)' 'sudo apt-get install -y git')"
fi

# fnm (Node version manager — the recommended way to get Node 24)
FNM_HINT=$(hint 'winget install --id Schniz.fnm -e   then add to PowerShell $PROFILE: fnm env --use-on-cd | Out-String | Invoke-Expression   AND to ~/.bashrc (Git Bash): eval "$(fnm env --shell bash)"' 'brew install fnm   then: eval "$(fnm env --use-on-cd)"' 'curl -fsSL https://fnm.vercel.app/install | bash   then: eval "$(fnm env --use-on-cd)"')
if command -v fnm >/dev/null 2>&1; then
  row fnm ok 0 "$(fnm --version | first_version)" "any" ""
else
  row fnm warn 0 "-" "recommended" "$FNM_HINT"
fi

# node
if command -v node >/dev/null 2>&1; then
  NODE_V=$(node -v | first_version)
  if [ "${NODE_V%%.*}" = "$NODE_MAJOR" ]; then
    row node ok 1 "$NODE_V" "$NODE_MAJOR.x" ""
  else
    row node old 1 "$NODE_V" "$NODE_MAJOR.x" "fnm install $NODE_MAJOR && fnm use $NODE_MAJOR   (or: fnm default $NODE_MAJOR)"
  fi
else
  if command -v fnm >/dev/null 2>&1; then
    # The common Windows case: PowerShell's $PROFILE runs fnm, but Git Bash (what just/make/Claude
    # Code use) has no ~/.bashrc — Node exists, it just isn't on THIS shell's PATH.
    case "$OS" in
      windows) FNM_INIT_HINT="fnm is installed but not initialised in this shell (Git Bash). Put: eval \"\$(fnm env --shell bash)\" in ~/.bashrc (create it; PowerShell's \$PROFILE does not apply here), open a new terminal; if fnm has no Node yet: fnm install $NODE_MAJOR && fnm default $NODE_MAJOR" ;;
      *) FNM_INIT_HINT="fnm is installed but not initialised in this shell. Put: eval \"\$(fnm env --use-on-cd)\" in ~/.zshrc or ~/.bashrc, open a new terminal; if fnm has no Node yet: fnm install $NODE_MAJOR && fnm default $NODE_MAJOR" ;;
    esac
    row node missing 1 "-" "$NODE_MAJOR.x" "$FNM_INIT_HINT"
  else
    row node missing 1 "-" "$NODE_MAJOR.x" "install fnm first (see above), then: fnm install $NODE_MAJOR && fnm use $NODE_MAJOR"
  fi
fi

# pnpm
if command -v pnpm >/dev/null 2>&1; then
  PNPM_V=$(pnpm -v 2>/dev/null | first_version)
  if [ "$PNPM_V" = "$PNPM_VERSION" ]; then
    row pnpm ok 1 "$PNPM_V" "$PNPM_VERSION" ""
  elif ver_ge "$PNPM_V" "${PNPM_VERSION%%.*}"; then
    row pnpm warn 1 "$PNPM_V" "$PNPM_VERSION" "corepack prepare pnpm@$PNPM_VERSION --activate   (or: npm i -g pnpm@$PNPM_VERSION)"
  else
    row pnpm old 1 "$PNPM_V" "$PNPM_VERSION" "corepack prepare pnpm@$PNPM_VERSION --activate   (or: npm i -g pnpm@$PNPM_VERSION)"
  fi
else
  row pnpm missing 1 "-" "$PNPM_VERSION" "corepack enable && corepack prepare pnpm@$PNPM_VERSION --activate   (needs Node first; fallback: npm i -g pnpm@$PNPM_VERSION)"
fi

# uv
UV_HINT=$(hint 'winget install --id astral-sh.uv -e   (or: powershell -c "irm https://astral.sh/uv/install.ps1 | iex")' 'brew install uv   (or: curl -LsSf https://astral.sh/uv/install.sh | sh)' 'curl -LsSf https://astral.sh/uv/install.sh | sh')
if command -v uv >/dev/null 2>&1; then
  UV_V=$(uv --version | first_version)
  if ver_ge "$UV_V" "$UV_MIN"; then
    row uv ok 1 "$UV_V" ">= $UV_MIN" ""
  else
    row uv old 1 "$UV_V" ">= $UV_MIN" "uv self update   (or reinstall: $UV_HINT)"
  fi
else
  row uv missing 1 "-" ">= $UV_MIN" "$UV_HINT"
fi

# python (managed by uv — no system Python needed)
if command -v uv >/dev/null 2>&1; then
  PY_PATH=$(uv python find "$PYTHON_VERSION" 2>/dev/null || true)
  if [ -n "$PY_PATH" ]; then
    PY_V=$("$PY_PATH" --version 2>/dev/null | first_version)
    row python ok 1 "${PY_V:-$PYTHON_VERSION}" "$PYTHON_VERSION" ""
  else
    row python missing 1 "-" "$PYTHON_VERSION" "uv python install $PYTHON_VERSION"
  fi
else
  row python missing 1 "-" "$PYTHON_VERSION" "install uv first, then: uv python install $PYTHON_VERSION"
fi

# bicep — the standalone CLI (what agents, `make infra-build` and the format hook call; `az bicep` is not on PATH as `bicep`)
BICEP_HINT=$(hint 'winget install --id Microsoft.Bicep -e' 'brew tap azure/bicep && brew install bicep' 'curl -Lo bicep https://github.com/Azure/bicep/releases/latest/download/bicep-linux-x64 && chmod +x bicep && sudo mv bicep /usr/local/bin/')
if command -v bicep >/dev/null 2>&1; then
  BICEP_V=$(bicep --version 2>/dev/null | first_version)
  if ver_ge "$BICEP_V" "$BICEP_MIN"; then
    row bicep ok 1 "$BICEP_V" ">= $BICEP_MIN" ""
  else
    row bicep old 1 "$BICEP_V" ">= $BICEP_MIN" "$BICEP_HINT"
  fi
else
  row bicep missing 1 "-" ">= $BICEP_MIN" "$BICEP_HINT"
fi

# task runner: just (recommended on Windows) or make
JUST_HINT=$(hint 'winget install --id Casey.Just -e' 'brew install just' 'sudo apt-get install -y just   (or: cargo install just; or the prebuilt binary from github.com/casey/just)')
if command -v just >/dev/null 2>&1; then
  row just ok 1 "$(just --version | first_version)" "just or make" ""
elif command -v make >/dev/null 2>&1; then
  row make ok 1 "$(make --version 2>/dev/null | first_version)" "just or make" ""
else
  row "just/make" missing 1 "-" "just or make" "$JUST_HINT"
fi

# docker (optional — only for the containerised stack / image builds)
DOCKER_HINT=$(hint 'winget install --id Docker.DockerDesktop -e   (needs WSL2: wsl --install, then reboot)' 'brew install --cask docker   then open Docker.app once' 'https://docs.docker.com/engine/install/  (then: sudo usermod -aG docker $USER, re-login)')
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    row docker ok 0 "$(docker --version | first_version)" "optional (Compose v2)" ""
  else
    row docker warn 0 "$(docker --version | first_version) (daemon not running)" "optional (Compose v2)" "start Docker Desktop / the docker service, then re-run"
  fi
else
  row docker warn 0 "-" "optional (Compose v2)" "$DOCKER_HINT"
fi

# gh (optional — /git-flow opens PRs with it)
GH_HINT=$(hint 'winget install --id GitHub.cli -e' 'brew install gh' 'see https://github.com/cli/cli/blob/trunk/docs/install_linux.md')
if command -v gh >/dev/null 2>&1; then
  row gh ok 0 "$(gh --version | first_version)" "optional" ""
else
  row gh warn 0 "-" "optional (PRs via /git-flow)" "$GH_HINT"
fi

# ODBC Driver 18 (optional — only to run the api locally against the dev Azure SQL database)
ODBC_HINT=$(hint 'winget install --id Microsoft.msodbcsql.18 -e   (needs admin)' 'brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release && HOMEBREW_ACCEPT_EULA=Y brew install msodbcsql18' 'https://learn.microsoft.com/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server  (apt: msodbcsql18 + unixodbc)')
ODBC_FOUND=""
case "$OS" in
  windows)
    [ -f "/c/Windows/System32/msodbcsql18.dll" ] && ODBC_FOUND="msodbcsql18.dll"
    ;;
  *)
    if command -v odbcinst >/dev/null 2>&1 && odbcinst -q -d 2>/dev/null | grep -q "ODBC Driver 18"; then
      ODBC_FOUND="ODBC Driver 18 for SQL Server"
    fi
    ;;
esac
if [ -n "$ODBC_FOUND" ]; then
  row odbc18 ok 0 "$ODBC_FOUND" "optional (local api vs Azure SQL)" ""
else
  row odbc18 warn 0 "-" "optional (local api vs Azure SQL)" "$ODBC_HINT"
fi

# az — required for developers (`what-if` / deploy to dev, Key Vault reads, `az acr login`); agents are prompted per call
AZ_HINT=$(hint 'winget install --id Microsoft.AzureCLI -e' 'brew install azure-cli' 'curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash')
if command -v az >/dev/null 2>&1; then
  row az ok 1 "installed" "any (then: az login)" ""
else
  row az missing 1 "-" "any (then: az login)" "$AZ_HINT"
fi

# ---- summary -----------------------------------------------------------------
if [ $JSON = 0 ]; then
  printf '\n  * = required.  OK = ready · MISSING/OLD = must fix · WARN = optional or not initialised in this shell\n'
  if [ $REQUIRED_FAILED = 1 ]; then
    printf '\nSome required tools are missing or too old. Run `/setup-dev-env` in Claude Code, or follow the\nhints above / docs/getting-started.md -> "Installing the tools". Open a NEW terminal after installing.\n'
  else
    printf '\nAll required tools are ready. Next: `make install` (or `just install`), then `make dev`.\n'
  fi
fi
exit $REQUIRED_FAILED
