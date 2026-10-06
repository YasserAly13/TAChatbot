# Wireframes — one file per page

Each page/screen of the application gets one markdown file here (`<page-slug>.md`), optionally
with an image (`<page-slug>.png` exported from the design tool). The web roadmap is planned
from these files, so they must say **what the page needs from the API** — that is what lets the
frontend and backend developers work in parallel (mocks until the endpoint exists).

## Template — copy into `<page-slug>.md`

```markdown
# Page: <Name> route: /<path>

## Purpose

One or two sentences: who uses it and what they accomplish.

## Layout

Describe regions top-to-bottom / left-to-right, or embed `![wireframe](<page-slug>.png)`.

## Elements

| Element | Type (list / form / button / stream / …) | Behaviour | Validation / limits |
| ------- | ---------------------------------------- | --------- | ------------------- |

## States

Empty · loading · error (with trace_id shown) · success · streaming (if any).

## API needs

| Action on the page | BFF route (/api/v1/…) | Upstream (/v1/…) | Exists? (yes / planned item id / mock) |
| ------------------ | --------------------- | ---------------- | -------------------------------------- |

## Auth / roles

Who may see it; what is hidden or disabled per role (or "no auth — internal only").

## Open questions
```
