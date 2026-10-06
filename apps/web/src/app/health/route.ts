import { withBff } from '@/lib/trace';
import { getObservabilityState } from '@/lib/observability';
import { log } from '@/lib/logger';

export const dynamic = 'force-dynamic';

export async function GET(req: Request): Promise<Response> {
  return withBff(req, ({ traceId }) => {
    const obs = getObservabilityState();
    log('info', 'health check', { route: '/health' });
    return Response.json({
      status: 'ok',
      service: 'web',
      trace_id: traceId,
      observability: obs.enabled ? 'enabled' : 'disabled',
      reason: obs.reason,
    });
  });
}
