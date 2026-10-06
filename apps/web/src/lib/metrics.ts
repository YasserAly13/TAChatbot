import { metrics, type Counter, type Histogram, type Meter } from '@opentelemetry/api';

/**
 * Custom-metric helpers (Phase 3 — see .claude/rules/60-observability.md).
 *
 * getMeter() returns namespaced meters ("ai-accelerator.<scope>") from the
 * GLOBAL MeterProvider. In degraded mode no provider is registered, so the
 * OTel API hands back its no-op proxy meter — feature code records metrics
 * unconditionally and never null-checks telemetry.
 *
 * CARDINALITY DISCIPLINE (required): metric attributes use BOUNDED value sets
 * only — route classes, methods, status classes, outcomes, targets — never
 * ids, names, emails, or paths with parameters. App Insights bills every
 * attribute combination as its own series (cap: 5,000 series/metric/day).
 */

const METER_PREFIX = 'ai-accelerator';

/** Namespaced meter accessor: getMeter("http") → meter "ai-accelerator.http". */
export function getMeter(scope: string): Meter {
  return metrics.getMeter(`${METER_PREFIX}.${scope}`);
}

/** Map an HTTP status code onto its bounded class ("2xx".."5xx", "unknown"). */
export function statusClass(status: number): string {
  if (!Number.isInteger(status) || status < 100 || status > 599) {
    return 'unknown';
  }
  return `${Math.floor(status / 100)}xx`;
}

/**
 * Bounded upstream-target label from a URL's origin, matched against the
 * configured upstream base URL (API_BASE_URL). Label set: "api" | "other".
 * Unknown/invalid URLs collapse to "other" so the attribute can never explode
 * in cardinality.
 */
export function resolveTarget(url: string, env: NodeJS.ProcessEnv = process.env): string {
  try {
    const origin = new URL(url).origin;
    if (env.API_BASE_URL && new URL(env.API_BASE_URL).origin === origin) {
      return 'api';
    }
    return 'other';
  } catch {
    return 'other';
  }
}

// Starter instruments (lazy: the global MeterProvider may register after this
// module loads; instruments created via the proxy meter re-bind automatically).
let serverDuration: Histogram | undefined;
let hopDuration: Histogram | undefined;
let upstreamFailures: Counter | undefined;

function serverDurationHistogram(): Histogram {
  serverDuration ??= getMeter('http').createHistogram('ai-accelerator.http.server.duration', {
    description: 'Inbound BFF request duration by route class and status class',
    unit: 'ms',
  });
  return serverDuration;
}

function hopDurationHistogram(): Histogram {
  hopDuration ??= getMeter('http').createHistogram('ai-accelerator.http.client.hop.duration', {
    description: 'Outbound service-to-service hop duration by target and outcome',
    unit: 'ms',
  });
  return hopDuration;
}

function upstreamFailureCounter(): Counter {
  upstreamFailures ??= getMeter('bff').createCounter('ai-accelerator.bff.upstream.failures', {
    description: 'BFF upstream calls that failed (network error or 5xx) by target and reason',
  });
  return upstreamFailures;
}

export interface ServerDurationSample {
  /** Bounded route identity: the handler's fixed path (or explicit routeClass). */
  routeClass: string;
  method: string;
  statusCode: number;
  durationMs: number;
}

/** Record one inbound BFF request duration sample. Best-effort — never throws. */
export function recordServerDuration(sample: ServerDurationSample): void {
  try {
    serverDurationHistogram().record(sample.durationMs, {
      route_class: sample.routeClass,
      method: sample.method,
      status_class: statusClass(sample.statusCode),
    });
  } catch {
    // Metrics are best-effort — never break the request path.
  }
}

export interface HopDurationSample {
  /** Bounded target label ("api" | "other"). */
  target: string;
  /** Bounded outcome: a status class ("2xx".."5xx") or "error". */
  outcome: string;
  durationMs: number;
}

/** Record one outbound chain-hop duration sample. Best-effort — never throws. */
export function recordHopDuration(sample: HopDurationSample): void {
  try {
    hopDurationHistogram().record(sample.durationMs, {
      target: sample.target,
      outcome: sample.outcome,
    });
  } catch {
    // Metrics are best-effort — never break the request path.
  }
}

export type UpstreamFailureReason = 'network_error' | 'http_5xx';

/** Count one failed BFF upstream call. Best-effort — never throws. */
export function recordUpstreamFailure(target: string, reason: UpstreamFailureReason): void {
  try {
    upstreamFailureCounter().add(1, { target, reason });
  } catch {
    // Metrics are best-effort — never break the request path.
  }
}

/** TEST-ONLY: drop cached instruments so a swapped provider takes effect. */
export function __resetMetricsForTests(): void {
  serverDuration = undefined;
  hopDuration = undefined;
  upstreamFailures = undefined;
}
