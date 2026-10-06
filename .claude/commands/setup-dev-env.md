---
description: Check this machine for every tool the repo needs (git, Node 24/fnm, pnpm 11.5.2, uv + Python 3.14, Bicep CLI, az, just/make; optional Docker, gh, ODBC 18), offer to install what is missing via winget/brew/apt, and hand over numbered manual steps when an install fails. Run before /init-project on a fresh machine.
argument-hint: [check-only]
---

Use the `setup-dev-env` skill. Mode: `$ARGUMENTS` (`check-only` = run `bash scripts/doctor.sh`, report, propose nothing).

Read-only until the developer answers **yes** to the proposed install list. Never `sudo`, never elevate, never disable TLS verification, never edit machine-wide settings. Print the doctor table as-is, then the install proposal (or the "all ready" message), and finish with the `## Environment` summary block from the skill — including the exact manual steps for anything that could not be installed.
