import { TRACE_HEADER } from '@/lib/trace';
import {
  recordHopDuration,
  recordUpstreamFailure,
  resolveTarget,
  statusClass,
} from '@/lib/metrics';

/**
 * Streaming pass-through for the BFF — the sanctioned way to forward a Server-Sent Events
 * response from the api (`/v1/.../stream`) to the browser. `fetchUpstream` is the wrong tool
 * for this: it forces `accept: application/json` and a 10 s timeout, and the callers read the
 * whole body.
 *
 * `streamUpstream` opens the upstream stream (forwards `x-trace-id`, asks for
 * `text/event-stream`, bounded by `STREAM_TIMEOUT_MS` unless a `signal` is given — a whole
 * answer, not a first-byte timeout) and records the hop metrics when the headers arrive.
 * `proxyStream` wraps the upstream body in a Response the browser can read incrementally
 * (no buffering hints, same-origin, trace id echoed).
 */
export const STREAM_TIMEOUT_MS = 300_000;

export async function streamUpstream(
  url: string,
  traceId: string,
  init?: RequestInit,
): Promise<Response> {
  const headers = new Headers(init?.headers);
  headers.set(TRACE_HEADER, traceId);
  headers.set('accept', 'text/event-stream');
  const signal = init?.signal ?? AbortSignal.timeout(STREAM_TIMEOUT_MS);
  const target = resolveTarget(url);
  const start = Date.now();
  try {
    const res = await fetch(url, { ...init, headers, signal, cache: 'no-store' });
    recordHopDuration({ target, outcome: statusClass(res.status), durationMs: Date.now() - start });
    if (res.status >= 500) {
      recordUpstreamFailure(target, 'http_5xx');
    }
    return res;
  } catch (err) {
    recordHopDuration({ target, outcome: 'error', durationMs: Date.now() - start });
    recordUpstreamFailure(target, 'network_error');
    throw err;
  }
}

/** Forward an upstream SSE response to the browser without buffering. */
export function proxyStream(upstream: Response, traceId: string): Response {
  const headers = new Headers({
    'content-type': upstream.headers.get('content-type') ?? 'text/event-stream; charset=utf-8',
    'cache-control': 'no-cache, no-transform',
    'x-accel-buffering': 'no',
    [TRACE_HEADER]: traceId,
  });
  return new Response(upstream.body, { status: upstream.status, headers });
}
