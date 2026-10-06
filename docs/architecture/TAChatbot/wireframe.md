# Team Assistant — wireframe `/chat`

_Paste-ready content for `docs/design/wireframes/chat.md`._

**Clickable version:** open [`wireframe.html`](wireframe.html) in a browser — the state buttons at
the top switch between the states listed below (no build, no server).

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

## States

| State     | What the user sees                                                                             |
| --------- | ---------------------------------------------------------------------------------------------- |
| empty     | no conversations: "No chats yet"; **+ New chat** creates one and focuses the input             |
| streaming | **Send** disabled; tokens appear; sources block appears as soon as the `sources` frame arrives |
| error     | a red line with the `error` code + `trace_id` under the last user message; input re-enabled    |
| done      | the assistant message with sources; the conversation moves to the top of the list              |
| reopened  | clicking a conversation loads its messages; the input continues that conversation              |

## Components

- Reuse `ChatThread`, `MessageInput`, `ChatPanel` from the template.
- Add `ConversationList` (rows with title + time, selected state, empty state, **+ New chat**).
- Add a `Sources` block under assistant messages (title → path).

## API needs (through the BFF, mocked until the api items are done)

| Action      | Call                                         |
| ----------- | -------------------------------------------- |
| page load   | `GET /api/v1/conversations`                  |
| + New chat  | `POST /api/v1/conversations`                 |
| click a row | `GET /api/v1/conversations/{id}`             |
| Send        | `POST /api/v1/conversations/{id}/ask/stream` |
