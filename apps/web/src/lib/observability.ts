/**
 * Fail-safe Azure Monitor / OpenTelemetry bootstrap.
 *
 * INIT-ORDER DISCIPLINE: Next.js cannot use a "first import" (its server is
 * already loaded when app code runs), so init happens in the framework's
 * sanctioned hook: `src/instrumentation.ts` `register()`, which Next runs once
 * per server instance BEFORE serving requests (nodejs runtime only).
 *
 * IDEMPOTENT: init + state live on `globalThis` under Symbol.for keys, so
 * calling initObservability() twice — or Next bundling this module into
 * SEPARATE module graphs (instrumentation vs route handlers, a real Next
 * quirk) — never double-registers the SDK, and every copy sees one state.
 *
 * SAMPLING IS PINNED EXPLICITLY: the distro (>=1.16.0) defaults to
 * RATE-LIMITED sampling (~5 traces/sec) — a silent telemetry cap. We always
 * pass `tracesPerSecond: 0` + `samplingRatio` (fixed percentage, default 1.0
 * = 100%, tunable via TRACE_SAMPLING_RATIO). The standard OTEL_TRACES_SAMPLER
 * / OTEL_TRACES_SAMPLER_ARG env vars still take precedence (the distro merges
 * env config after code options).
 *
 * CLOUD ROLE IDENTITY: service.name (→ cloud role name) and
 * service.instance.id (→ cloud role instance) are defaulted via the standard
 * OTEL_SERVICE_NAME / OTEL_RESOURCE_ATTRIBUTES env vars (read natively by the
 * distro's env resource detector — no @opentelemetry/resources dependency
 * needed). Defaults are append-only: operator-provided values are NEVER
 * overridden. service.namespace is deliberately not set.
 */

import { hostname } from 'node:os';

interface ObservabilityState {
  enabled: boolean;
  reason: string;
}

const DEFAULT_SERVICE_NAME = 'team-assistant-web';

/** Process-global keys (Symbol.for registry) shared across Next module graphs. */
const INIT_FLAG = Symbol.for('team-assistant.web.observability.initialized');
const STATE_KEY = Symbol.for('team-assistant.web.observability.state');

type GlobalStore = Record<symbol, unknown>;
const globalStore = globalThis as unknown as GlobalStore;

export interface SamplingConfig {
  /** Effective fixed-percentage ratio in [0, 1]. */
  ratio: number;
  /** Where the value came from (for the startup log line). */
  source: 'default' | 'TRACE_SAMPLING_RATIO' | 'OTEL_TRACES_SAMPLER';
}

/**
 * Resolve the fixed-percentage sampling ratio.
 *
 * - `OTEL_TRACES_SAMPLER` set  -> the standard OTel env config drives sampling
 *   (distro env config overrides code options); we report that as the source.
 * - `TRACE_SAMPLING_RATIO` set -> parsed float in [0, 1]; invalid values warn
 *   and fall back to 1.0 (never crash, never silently under-sample).
 * - otherwise                  -> 1.0 (100%).
 */
export function resolveSamplingRatio(env: NodeJS.ProcessEnv = process.env): SamplingConfig {
  if (env.OTEL_TRACES_SAMPLER && env.OTEL_TRACES_SAMPLER.trim() !== '') {
    return { ratio: 1, source: 'OTEL_TRACES_SAMPLER' };
  }
  const raw = env.TRACE_SAMPLING_RATIO;
  if (raw === undefined || raw.trim() === '') {
    return { ratio: 1, source: 'default' };
  }
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1) {
    process.stderr.write(
      `Invalid TRACE_SAMPLING_RATIO "${raw}" — expected a number in [0, 1]; using 1.0\n`,
    );
    return { ratio: 1, source: 'default' };
  }
  return { ratio: parsed, source: 'TRACE_SAMPLING_RATIO' };
}

export type TelemetryAuthMode = 'connection_string' | 'managed_identity';

export type AuthModeConfig = { mode: TelemetryAuthMode; clientId?: string } | { error: string };

/**
 * Resolve the telemetry ingestion auth mode (Phase 4 ingestion hardening).
 *
 * - unset/"" or "connection_string" -> connection-string ingestion (default).
 * - "managed_identity" -> Entra ID ingestion via ManagedIdentityCredential
 *   (system-assigned, or user-assigned when
 *   TELEMETRY_MANAGED_IDENTITY_CLIENT_ID is set). Requires the identity to
 *   hold "Monitoring Metrics Publisher" on the App Insights component.
 * - anything else -> ERROR. A mistyped value must degrade VISIBLY
 *   (observability disabled, reason on /health) — never silently fall back
 *   to unauthenticated ingestion.
 */
export function resolveAuthMode(env: NodeJS.ProcessEnv = process.env): AuthModeConfig {
  const raw = (env.TELEMETRY_AUTH_MODE ?? '').trim();
  if (raw === '' || raw === 'connection_string') {
    return { mode: 'connection_string' };
  }
  if (raw === 'managed_identity') {
    const clientId = env.TELEMETRY_MANAGED_IDENTITY_CLIENT_ID?.trim();
    return { mode: 'managed_identity', ...(clientId ? { clientId } : {}) };
  }
  return {
    error: `invalid TELEMETRY_AUTH_MODE "${raw}" — expected "connection_string" or "managed_identity"`,
  };
}

/** True when OTEL_RESOURCE_ATTRIBUTES already carries the given attribute key. */
function hasResourceAttribute(attrs: string, key: string): boolean {
  return attrs.split(',').some((pair) => pair.trim().startsWith(`${key}=`));
}

/**
 * Default the OTel resource identity via env vars (read by the distro's env
 * resource detector). Append-only: operator-provided OTEL_SERVICE_NAME /
 * OTEL_RESOURCE_ATTRIBUTES values are never overridden.
 *
 * - service.name        -> App Insights cloud role name (default: team-assistant-web)
 * - service.instance.id -> cloud role instance (container replica name, then
 *   HOSTNAME, then os.hostname() fallback)
 */
export function applyResourceDefaults(env: NodeJS.ProcessEnv = process.env): void {
  const attrs = env.OTEL_RESOURCE_ATTRIBUTES ?? '';
  if (!env.OTEL_SERVICE_NAME && !hasResourceAttribute(attrs, 'service.name')) {
    env.OTEL_SERVICE_NAME = DEFAULT_SERVICE_NAME;
  }
  if (!hasResourceAttribute(attrs, 'service.instance.id')) {
    const instanceId = env.CONTAINER_APP_REPLICA_NAME || env.HOSTNAME || hostname();
    env.OTEL_RESOURCE_ATTRIBUTES = attrs
      ? `${attrs},service.instance.id=${instanceId}`
      : `service.instance.id=${instanceId}`;
  }
}

function setState(state: ObservabilityState): void {
  globalStore[STATE_KEY] = state;
}

/** Current observability state for health/diagnostics. */
export function getObservabilityState(): ObservabilityState {
  const state = globalStore[STATE_KEY] as ObservabilityState | undefined;
  if (state) {
    return { ...state };
  }
  // Not initialized in this process (e.g. a bundle where instrumentation.ts
  // never ran, or tests). Derive a best-effort, side-effect-free state from
  // the environment so /health reports an accurate, consistent reason
  // (matching the api wording).
  const connectionString = process.env.APPLICATIONINSIGHTS_CONNECTION_STRING;
  if (!connectionString || connectionString.trim() === '') {
    return { enabled: false, reason: 'no Azure connection string' };
  }
  return { enabled: true, reason: 'ok' };
}

/**
 * Initialize Azure Monitor OpenTelemetry. Idempotent (process-global guard)
 * and fail-safe (never throws). Intended to be called once from
 * `instrumentation.ts` (Node.js runtime only).
 */
export async function initObservability(): Promise<ObservabilityState> {
  if (globalStore[INIT_FLAG]) {
    return getObservabilityState();
  }
  globalStore[INIT_FLAG] = true;

  applyResourceDefaults();

  // Ingestion auth mode is validated FIRST: a mistyped value disables
  // telemetry visibly instead of silently ingesting unauthenticated.
  const auth = resolveAuthMode();
  if ('error' in auth) {
    setState({ enabled: false, reason: auth.error });
    process.stderr.write(
      `Observability disabled: ${auth.error} — refusing to fall back to unauthenticated ingestion; running with local stdout logging only\n`,
    );
    return getObservabilityState();
  }

  const connectionString = process.env.APPLICATIONINSIGHTS_CONNECTION_STRING;

  if (!connectionString || connectionString.trim() === '') {
    setState({ enabled: false, reason: 'no Azure connection string' });
    process.stderr.write(
      'Observability disabled: no Azure connection string — running with local stdout logging only\n',
    );
    return getObservabilityState();
  }

  try {
    // Aliased away from the `use*` name so linters don't mistake Azure's
    // useAzureMonitor() for a React Hook — it's the SDK's setup function.
    const { useAzureMonitor: configureAzureMonitor } = await import('@azure/monitor-opentelemetry');

    // Entra ID ingestion (Phase 4 hardening): the credential makes the
    // exporter send AAD-authenticated telemetry; pairs with DisableLocalAuth
    // on the component (infra/main.bicep).
    let credential;
    if (auth.mode === 'managed_identity') {
      const { ManagedIdentityCredential } = await import('@azure/identity');
      credential = auth.clientId
        ? new ManagedIdentityCredential({ clientId: auth.clientId })
        : new ManagedIdentityCredential();
    }

    const sampling = resolveSamplingRatio();
    configureAzureMonitor({
      azureMonitorExporterOptions: {
        connectionString,
        ...(credential ? { credential } : {}),
      },
      // Pin fixed-percentage sampling: tracesPerSecond MUST be 0, otherwise
      // the distro's rate-limited default (~5 traces/sec) silently drops
      // telemetry. OTEL_TRACES_SAMPLER* env vars still override these.
      samplingRatio: sampling.ratio,
      tracesPerSecond: 0,
    });

    // Gap-closers the distro does NOT register (verified in 1.18.1 — its
    // instrumentation set is azureSdk/http/mongoDb/mySql/postgreSql/redis):
    //   - undici: global `fetch` (fetchUpstream) emits NO dependency spans
    //     otherwise. Based on diagnostics_channel, so registering AFTER
    //     Next's server (and undici) already loaded still works.
    //   - runtime-node: event-loop lag/utilization, GC, heap runtime metrics.
    // Both use the global providers configureAzureMonitor just registered.
    const [
      { registerInstrumentations },
      { UndiciInstrumentation },
      { RuntimeNodeInstrumentation },
    ] = await Promise.all([
      import('@opentelemetry/instrumentation'),
      import('@opentelemetry/instrumentation-undici'),
      import('@opentelemetry/instrumentation-runtime-node'),
    ]);
    registerInstrumentations({
      instrumentations: [new UndiciInstrumentation(), new RuntimeNodeInstrumentation()],
    });

    setState({ enabled: true, reason: 'ok' });
  } catch (err) {
    // Swallow: never crash the server because telemetry failed to start.
    const reason = err instanceof Error ? err.message : 'unknown initialization error';
    setState({ enabled: false, reason });
    process.stderr.write(
      `Observability disabled: initialization failed (${reason}) — running with local stdout logging only\n`,
    );
  }

  return getObservabilityState();
}

/** TEST-ONLY: clear the process-global init guard + state between test cases. */
export function __resetObservabilityForTests(): void {
  delete globalStore[INIT_FLAG];
  delete globalStore[STATE_KEY];
}
