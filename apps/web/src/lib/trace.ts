import { AsyncLocalStorage } from 'node:async_hooks';
import { randomBytes } from 'node:crypto';
import {
  recordHopDuration,
  recordServerDuration,
  recordUpstreamFailure,
  resolveTarget,
  statusClass,
} from '@/lib/metrics';

/**
 * Distributed-tracing primitives for the `web` service.
 *
 * SHARED CONTRACT (must match the api service):
 *   - trace_id = origin(4 hex) + env(1 hex) + random(27 hex) = 32 hex total
 *   - this service's trace origin = "0eb0"
 *   - canonical header = "x-trace-id" (lowercase)
 */

/** Trace origin for the web service (4 hex). */
export const ORIGIN = '0eb0';

/** Canonical inbound/outbound trace header (lowercase). */
export const TRACE_HEADER = 'x-trace-id';

/** 32-hex trace-id validation regex. */
export const TRACE_ID_REGEX = /^[0-9a-f]{32}$/;

/** APP_ENV -> single hex digit. Unknown/missing => local (0). */
export function envHex(appEnv?: string | null): string {
  switch ((appEnv ?? '').toLowerCase()) {
    case 'local':
      return '0';
    case 'dev':
      return '1';
    case 'staging':
      return '2';
    case 'prod':
      return '3';
    case 'sandbox':
      return '4';
    default:
      return '0'; // treat unknown/missing as local
  }
}

/** Generate a web-origin trace id: 0eb0 + envHex + 27 random hex = 32 hex. */
export function generateTraceId(): string {
  const random = randomBytes(14).toString('hex').slice(0, 27);
  return `${ORIGIN}${envHex(process.env.APP_ENV)}${random}`;
}

/** Validate a trace id against the shared 32-hex contract. */
export function isValidTraceId(s: string | null | undefined): s is string {
  return typeof s === 'string' && TRACE_ID_REGEX.test(s);
}

interface TraceStore {
  traceId: string;
}

const store = new AsyncLocalStorage<TraceStore>();

/** Read the trace id for the current request scope (undefined outside a scope). */
export function getTraceId(): string | undefined {
  return store.getStore()?.traceId;
}

/** Run `fn` with the given trace id bound to the async-local store. */
export function runWithTrace<T>(traceId: string, fn: () => T): T {
  return store.run({ traceId }, fn);
}

/**
 * Resolve the trace id for an inbound request: adopt a valid inbound
 * `x-trace-id`, otherwise mint a fresh web-origin one.
 */
export function resolveInboundTraceId(req: Request): string {
  const inbound = req.headers.get(TRACE_HEADER);
  return isValidTraceId(inbound) ? inbound : generateTraceId();
}

/** Context handed to a BFF handler. */
export interface BffContext {
  traceId: string;
  req: Request;
}

/** Options for `withBff`. */
export interface WithBffOptions {
  /**
   * Bounded route identity for the request-duration metric. Defaults to the
   * request URL's pathname — fine for the fixed folder routes this BFF has
   * today, but a handler under a dynamic segment (e.g. `[id]`) MUST pass its
   * pattern here (`/api/v1/things/[id]`) to keep metric cardinality bounded.
   */
  routeClass?: string;
}

/**
 * BFF wrapper: resolves/adopts the trace id, runs the handler inside the ALS
 * store, guarantees `x-trace-id` is echoed on the response, and records the
 * request-duration metric by route class and status class.
 */
export async function withBff(
  req: Request,
  handler: (ctx: BffContext) => Promise<Response> | Response,
  options?: WithBffOptions,
): Promise<Response> {
  const traceId = resolveInboundTraceId(req);
  let routeClass = options?.routeClass;
  if (!routeClass) {
    try {
      routeClass = new URL(req.url).pathname;
    } catch {
      routeClass = 'unknown';
    }
  }
  const start = Date.now();
  return runWithTrace(traceId, async () => {
    try {
      const res = await handler({ traceId, req });
      res.headers.set(TRACE_HEADER, traceId);
      recordServerDuration({
        routeClass,
        method: req.method,
        statusCode: res.status,
        durationMs: Date.now() - start,
      });
      return res;
    } catch (err) {
      // An uncaught handler error surfaces as a framework 500 — record it,
      // then rethrow unchanged.
      recordServerDuration({
        routeClass,
        method: req.method,
        statusCode: 500,
        durationMs: Date.now() - start,
      });
      throw err;
    }
  });
}

/**
 * Fetch an upstream service — the ONLY sanctioned HTTP client in this app
 * (bare `fetch` is a review-blocking violation, see .claude/rules/30-nextjs.md).
 *
 * Always forwards the canonical `x-trace-id` header so the same id flows
 * through every hop, records the chain-hop duration metric, and counts
 * upstream failures (network error / 5xx). The W3C `traceparent` header and
 * the AppDependencies span come from the undici instrumentation registered at
 * init (Phase 2).
 *
 * Every call is BOUNDED: Node's global fetch has no implicit timeout, so unless
 * the caller supplies its own `signal`, the request aborts after
 * `UPSTREAM_TIMEOUT_MS` (rule 50 → External HTTP: never an unbounded wait).
 */
export const UPSTREAM_TIMEOUT_MS = 10_000;

export async function fetchUpstream(
  url: string,
  traceId: string,
  init?: RequestInit,
): Promise<Response> {
  const headers = new Headers(init?.headers);
  headers.set(TRACE_HEADER, traceId);
  headers.set('accept', 'application/json');
  const signal = init?.signal ?? AbortSignal.timeout(UPSTREAM_TIMEOUT_MS);
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
