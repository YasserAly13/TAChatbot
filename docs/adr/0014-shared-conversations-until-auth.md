# ADR-0014: Conversations are shared, with no owner, until auth lands

|        |            |
| ------ | ---------- |
| Status | Accepted   |
| Date   | 2026-10-06 |

## Context

Team Assistant stores conversations and messages in Azure SQL (`TAChatbot/architecture.md` → B4)
and lists them on `/chat`. The template ships no auth: projects are internal-only until the Okta
module (roadmap Phase 8, needs its own ADR and threat model). Without an identity there is nothing
to own a conversation by, so either everything is shared or history is kept per browser.

## Decision

Conversations carry no owner column: every user of the deployment can list, read and continue
every conversation until Okta lands, at which point an `owner_id` column, a backfill decision and
per-user filtering are added under the auth ADR.

## Consequences

- Good: the simplest data model; F2 (history) ships without any identity work.
- Bad: anything one person types is visible to every other user — the UI must not imply privacy.
- Bad: adding ownership later needs a migration on a populated `conversations` table and a rule
  for existing rows (assign to nobody / an admin / delete).

## Alternatives considered

- **Per-browser history (an anonymous id in a cookie or `localStorage`)** — rejected: it is not
  a security boundary, and it would be thrown away when Okta lands.
- **No stored history until auth** — rejected: F2 is a core feature of the release.

## References

- Related ADRs: ADR-0013 (local-only, which today limits users to the developer)
- Docs: `docs/architecture/ARCHITECTURE.md` → B7; `.claude/rules/50-security.md`
