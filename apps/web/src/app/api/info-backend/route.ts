import { withBff, fetchUpstream } from '@/lib/trace';
import { log } from '@/lib/logger';

export const dynamic = 'force-dynamic';

export async function GET(req: Request): Promise<Response> {
  return withBff(req, async ({ traceId }) => {
    const base = process.env.API_BASE_URL ?? 'http://localhost:8000';
    const url = `${base}/info`;

    log('info', 'bff inbound', { route: '/api/info-backend' });

    try {
      log('info', 'bff upstream call', { upstream: url, target: 'api' });
      const res = await fetchUpstream(url, traceId);
      const data = await res.json();
      log('info', 'bff upstream ok', {
        upstream: url,
        status: res.status,
      });
      return Response.json(data, { status: res.status });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'upstream error';
      log('error', 'bff upstream failed', { upstream: url, error: message });
      return Response.json(
        { error: 'upstream_unreachable', target: 'api', trace_id: traceId },
        { status: 502 },
      );
    }
  });
}
