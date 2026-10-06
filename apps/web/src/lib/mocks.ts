import { log } from '@/lib/logger';
import { sseStreamFromFrames } from '@/lib/sse';
import { TRACE_HEADER } from '@/lib/trace';

/**
 * Mock-upstream mode — how the frontend developer works ahead of the backend.
 *
 * With `MOCK_UPSTREAM=true` (server-side env, never `NEXT_PUBLIC_*`) a BFF route serves a
 * fixture from `src/mocks/` instead of calling the api. Fixtures are typed against the API
 * contract (`src/lib/api-types.ts`, generated from `docs/reference/openapi.json`), so when the
 * real endpoint lands the switch is deleting the `isMockUpstream()` branch — nothing else.
 *
 * Every mocked response carries `x-mock-upstream: true` and logs a line, so a mock can never
 * pass for real data unnoticed. Mock mode is refused when `APP_ENV=prod`.
 */
export const MOCK_HEADER = 'x-mock-upstream';

export function isMockUpstream(): boolean {
  if (process.env.MOCK_UPSTREAM !== 'true') return false;
  if ((process.env.APP_ENV ?? '').toLowerCase() === 'prod') {
    log('error', 'MOCK_UPSTREAM ignored in prod', {});
    return false;
  }
  return true;
}

export function mockJson(fixture: unknown, traceId: string, status = 200): Response {
  log('info', 'bff mock upstream', { kind: 'json', status });
  return Response.json(fixture, {
    status,
    headers: { [MOCK_HEADER]: 'true', [TRACE_HEADER]: traceId },
  });
}

export function mockSse(frames: string[], traceId: string, delayMs = 20): Response {
  log('info', 'bff mock upstream', { kind: 'sse', frames: frames.length });
  return new Response(sseStreamFromFrames(frames, delayMs), {
    status: 200,
    headers: {
      'content-type': 'text/event-stream; charset=utf-8',
      'cache-control': 'no-cache, no-transform',
      [MOCK_HEADER]: 'true',
      [TRACE_HEADER]: traceId,
    },
  });
}
