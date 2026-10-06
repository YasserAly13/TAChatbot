import { withBff, fetchUpstream } from '@/lib/trace';
import { log } from '@/lib/logger';
import { isMockUpstream, mockJson } from '@/lib/mocks';
import { askFixture } from '@/mocks/assistant';

export const dynamic = 'force-dynamic';

/** A model answer routinely exceeds fetchUpstream's 10 s default — bound it explicitly. */
export const ASK_TIMEOUT_MS = 120_000;

/**
 * POST /api/v1/assistant/ask  → api POST /v1/assistant/ask  (non-streaming)
 * Example business route: the api ships no /v1/assistant yet, so this runs against the
 * fixture with MOCK_UPSTREAM=true until a project adds the route (feature-scaffold `ai`).
 */
export async function POST(req: Request): Promise<Response> {
  return withBff(
    req,
    async ({ traceId }) => {
      const body = (await req.json().catch(() => null)) as { question?: unknown } | null;
      const question = typeof body?.question === 'string' ? body.question.trim() : '';
      if (!question) {
        return Response.json({ error: 'invalid_request', trace_id: traceId }, { status: 400 });
      }
      log('info', 'bff inbound', { route: '/api/v1/assistant/ask' });
      if (isMockUpstream()) return mockJson(askFixture, traceId);

      const base = process.env.API_BASE_URL ?? 'http://localhost:8000';
      const url = `${base}/v1/assistant/ask`;
      try {
        log('info', 'bff upstream call', { upstream: url, target: 'api' });
        const res = await fetchUpstream(url, traceId, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ question }),
          signal: AbortSignal.timeout(ASK_TIMEOUT_MS),
        });
        const data = await res.json();
        log('info', 'bff upstream ok', { upstream: url, status: res.status });
        return Response.json(data, { status: res.status });
      } catch (err) {
        const message = err instanceof Error ? err.message : 'upstream error';
        log('error', 'bff upstream failed', { upstream: url, error: message });
        return Response.json(
          { error: 'upstream_unreachable', target: 'api', trace_id: traceId },
          { status: 502 },
        );
      }
    },
    { routeClass: '/api/v1/assistant/ask' },
  );
}
