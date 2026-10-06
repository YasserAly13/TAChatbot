# Page: Chat route: /chat

## Purpose

Any team member asks questions about the team's documentation and gets streamed answers with
citations; past conversations can be reopened and continued.

## Layout

**Clickable version:** open [`chat.html`](chat.html) in a browser — the state buttons at the top
switch between the states listed below (no build, no server).

Two columns: conversations on the left, the thread on the right, the input at the bottom. Below
768 px the list collapses into a drawer button.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Team Assistant                                            [ + New chat ]    │
├──────────────────┬───────────────────────────────────────────────────────────┤
│ Conversations    │                                                           │
│ ──────────────── │   You:  How does trace_id propagation work?               │
│ ● Trace ids      │                                                           │
│   today 10:12    │   Assistant:  The trace id is minted by the BFF …         │
│ ▸ Error contract │   (streams in)                                            │
│   today 09:40    │   Sources: trace_id — the invariant (README.md) ·         │
│ ▸ Onboarding     │            Observability contract (.claude/rules/60-…)    │
│   yesterday      │                                                           │
│                  │   You:  And on the api side?                              │
│                  │   Assistant:  … (uses the last 10 messages as history)    │
│ (empty state:    ├───────────────────────────────────────────────────────────┤
│  "No chats yet") │  [ Ask a question…                             ] [ Send ] │
│                  │   0 / 4,000                                               │
└──────────────────┴───────────────────────────────────────────────────────────┘
```

## Elements

| Element            | Type   | Behaviour                                                              | Validation / limits     |
| ------------------ | ------ | ---------------------------------------------------------------------- | ----------------------- |
| `ConversationList` | list   | rows with title + time, selected state, empty state; click reopens one | `limit=50` newest first |
| **+ New chat**     | button | creates a conversation and focuses the input                           | —                       |
| `ChatThread`       | stream | user and assistant messages; tokens stream in                          | —                       |
| `Sources`          | list   | under each assistant message: document title → path                    | —                       |
| `MessageInput`     | form   | question box + **Send**; character counter                             | ≤ 4,000 characters      |

Reuse `ChatThread`, `MessageInput`, `ChatPanel` from the template; add `ConversationList` and
`Sources`.

## States

| State     | What the user sees                                                                             |
| --------- | ---------------------------------------------------------------------------------------------- |
| empty     | no conversations: "No chats yet"; **+ New chat** creates one and focuses the input             |
| streaming | **Send** disabled; tokens appear; sources block appears as soon as the `sources` frame arrives |
| error     | a red line with the `error` code + `trace_id` under the last user message; input re-enabled    |
| done      | the assistant message with sources; the conversation moves to the top of the list              |
| reopened  | clicking a conversation loads its messages; the input continues that conversation              |

## API needs

Through the BFF, mocked (`MOCK_UPSTREAM`) until the api items are done. Contract:
[`TAChatbot/architecture.md`](../../architecture/TAChatbot/architecture.md) → B4a.

| Action on the page | BFF route (/api/v1/…)                        | Upstream (/v1/…)                         | Exists?                   |
| ------------------ | -------------------------------------------- | ---------------------------------------- | ------------------------- |
| page load          | `GET /api/v1/conversations`                  | `GET /v1/conversations`                  | planned (`/plan-roadmap`) |
| + New chat         | `POST /api/v1/conversations`                 | `POST /v1/conversations`                 | planned                   |
| click a row        | `GET /api/v1/conversations/{id}`             | `GET /v1/conversations/{id}`             | planned                   |
| Send               | `POST /api/v1/conversations/{id}/ask/stream` | `POST /v1/conversations/{id}/ask/stream` | planned                   |

## Auth / roles

No auth — internal only; every user sees every conversation (`ARCHITECTURE.md` → B7).

## Open questions

None.
