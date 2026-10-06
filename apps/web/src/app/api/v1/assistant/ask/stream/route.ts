import { withBff } from '@/lib/trace';
import { log } from '@/lib/logger';
import { isMockUpstream, mockSse } from '@/lib/mocks';
import { proxyStream, streamUpstream } from '@/lib/stream';
import { sseFrame } from '@/lib/sse';
import { askStreamFrames } from '@/mocks/assistant';

export const dynamic = 'force-dynamic';

/**
 * POST /api/v1/assistant/ask/stream → api POST /v1/assistant/ask/stream (Server-Sent Events)
 * Streams the api's frames to the browser unchanged. In mock mode the fixture frames are
 * paced to look like a real answer.
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
      log('info', 'bff inbound', { route: '/api/v1/assistant/ask/stream' });
      if (isMockUpstream()) return mockSse(askStreamFrames, traceId);

      const base = process.env.API_BASE_URL ?? 'http://localhost:8000';
      const url = `${base}/v1/assistant/ask/stream`;
      try {
        log('info', 'bff upstream stream', { upstream: url, target: 'api' });
        const upstream = await streamUpstream(url, traceId, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ question }),
        });
        if (!upstream.ok || !upstream.body) {
          log('error', 'bff upstream stream rejected', { upstream: url, status: upstream.status });
          return Response.json(
            { error: 'upstream_error', target: 'api', trace_id: traceId },
            { status: 502 },
          );
        }
        return proxyStream(upstream, traceId);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'upstream error';
        log('error', 'bff upstream failed', { upstream: url, error: message });
        // Still an SSE body so the client's stream parser sees a terminal frame.
        return new Response(sseFrame('error', { error_kind: 'upstream_unreachable' }), {
          status: 502,
          headers: { 'content-type': 'text/event-stream; charset=utf-8' },
        });
      }
    },
    { routeClass: '/api/v1/assistant/ask/stream' },
  );
}
