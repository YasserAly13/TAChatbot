# `src/mocks/` — fixtures for working ahead of the backend

The frontend developer builds against **fixtures** until the api endpoint exists, then deletes
the mock branch. The rules:

- One module per feature (`assistant.ts`, `<feature>.ts`) exporting plain data (JSON fixtures)
  and, for streaming routes, an array of SSE frames built with `sseFrame()`.
- **Type every fixture against the contract**: import the generated types from
  `@/lib/api-types` (`docs/reference/openapi.json` → `make openapi`). If the endpoint is not in
  the contract yet, write the type you expect next to the fixture and mark it
  `// TODO(contract): replace with api-types once api:<roadmap id> lands`.
- A BFF route uses the fixture only inside `if (isMockUpstream())` (`@/lib/mocks`) — the real
  call stays in the same handler, so removing the mock is a one-line deletion.
- Mock mode is **server-side** (`MOCK_UPSTREAM=true` in `apps/web/.env.local`), never exposed
  to the browser, refused in `prod`, and every mocked response carries `x-mock-upstream: true`.
- Fixtures are excluded from coverage; the routes that use them are tested in both modes
  (`routes.test.ts` next to the route).
