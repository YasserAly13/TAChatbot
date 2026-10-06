import { logs, SeverityNumber } from '@opentelemetry/api-logs';
import pino from 'pino';
import { getObservabilityState } from '@/lib/observability';
import { getTraceId } from '@/lib/trace';

/**
 * Structured JSON logging to stdout (always on).
 *
 * Every emitted line contains at least:
 *   timestamp, level, service, origin, env, trace_id, message
 *
 * pino's defaults (`time`, `msg`, numeric levels) are remapped via
 * formatters/messageKey/timestamp so the keys match the shared contract.
 *
 * PHASE 1 — log pipeline (see .claude/rules/60-observability.md):
 *
 * - REDACTION AT SOURCE: pino's `redact` option censors the default
 *   secret-bearing fields (DEFAULT_REDACTED_FIELDS) to "[redacted]" during
 *   serialization — BEFORE any sink (stdout or Azure) sees the line.
 *   Extensible per logger via `buildLogger({ redactPaths })`.
 * - OTEL LOGS BRIDGE: the Azure distro only collects bunyan/winston — pino is
 *   NOT on its list — so every serialized line is teed through the OTel Logs
 *   API. The distro's NodeSDK registers the global LoggerProvider (reachable
 *   across Next's module graphs via the api-logs Symbol.for global); in
 *   degraded mode the bridge short-circuits. Emitting happens synchronously
 *   inside the request context, so the SDK attaches the active span context
 *   (=> AppTraces.operation_Id matches AppRequests). A bridge failure can
 *   never break local logging. Per-logger opt-out:
 *   `buildLogger({ telemetryBridge: false })`.
 * - NON-BLOCKING SINK: stdout goes through `pino.destination({ sync: false })`
 *   (buffered, off the request path), with a best-effort synchronous flush of
 *   every sink at process exit so shutdown lines aren't lost.
 */

const SERVICE = 'web';
const ORIGIN = '0eb0';
const OTEL_LOGGER_NAME = 'team-assistant-web';

export const REDACTION_CENSOR = '[redacted]';

/**
 * Default secret-bearing log fields, censored before ANY sink sees the line.
 * Matched at the top level and one level deep (`*.field`). Field names in this
 * repo's logs are lowercase; both hyphen and underscore variants are listed.
 */
export const DEFAULT_REDACTED_FIELDS = [
  'authorization',
  'cookie',
  'set-cookie',
  'set_cookie',
  'x-api-key',
  'token',
  'access_token',
  'refresh_token',
  'id_token',
  'password',
  'secret',
  'client_secret',
  'api_key',
  'apiKey',
  'connection_string',
  'connectionString',
] as const;

/** pino/fast-redact paths for a field: top level + one level deep. */
function redactPathsFor(field: string): string[] {
  const key = /^[A-Za-z_$][\w$]*$/.test(field) ? field : `["${field}"]`;
  const nested = key.startsWith('[') ? `*${key}` : `*.${key}`;
  return [key, nested];
}

export const DEFAULT_REDACT_PATHS: string[] = DEFAULT_REDACTED_FIELDS.flatMap(redactPathsFor);

const PINO_LEVEL_TO_SEVERITY: Record<string, SeverityNumber> = {
  trace: SeverityNumber.TRACE,
  debug: SeverityNumber.DEBUG,
  info: SeverityNumber.INFO,
  warn: SeverityNumber.WARN,
  error: SeverityNumber.ERROR,
  fatal: SeverityNumber.FATAL,
};

/** Minimal sink contract (SonicBoom, or an in-memory fake in tests). */
export interface LogDestination {
  write(line: string): unknown;
  flushSync?(): void;
}

const sinks = new Set<LogDestination>();
let exitFlushInstalled = false;

function registerSink(dest: LogDestination): void {
  sinks.add(dest);
  if (!exitFlushInstalled) {
    exitFlushInstalled = true;
    // 'exit' handlers must be synchronous — flushSync is exactly that.
    process.on('exit', flushAllLogSinks);
  }
}

/** Best-effort synchronous flush of every registered sink (runs at exit). */
export function flushAllLogSinks(): void {
  for (const dest of sinks) {
    try {
      dest.flushSync?.();
    } catch {
      // Flushing is best-effort; never throw during shutdown.
    }
  }
}

/**
 * Map a parsed pino record to OTel log attributes: primitives pass through,
 * objects are JSON-stringified, and level/message/timestamp are dropped
 * (they map to severity/body/timestamp on the record itself).
 */
export function otelLogAttributes(
  record: Record<string, unknown>,
): Record<string, string | number | boolean> {
  const attributes: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(record)) {
    if (key === 'level' || key === 'message' || key === 'timestamp') continue;
    if (value === null || value === undefined) continue;
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      attributes[key] = value;
    } else {
      try {
        attributes[key] = JSON.stringify(value);
      } catch {
        // Unserializable attribute — drop it rather than fail the bridge.
      }
    }
  }
  return attributes;
}

/**
 * Wrap a destination so every serialized line is (1) written locally and
 * (2) re-emitted through the OTel Logs API when observability is enabled.
 * The local write always happens first and is never affected by the bridge.
 */
export function createTeeStream(
  dest: LogDestination,
  options: { bridge: boolean; loggerName?: string } = { bridge: true },
): LogDestination {
  const loggerName = options.loggerName ?? OTEL_LOGGER_NAME;
  return {
    write(line: string): void {
      dest.write(line);
      if (!options.bridge) return;
      try {
        if (!getObservabilityState().enabled) return;
        const record = JSON.parse(line) as Record<string, unknown>;
        const level = typeof record.level === 'string' ? record.level : 'info';
        logs.getLogger(loggerName).emit({
          severityNumber: PINO_LEVEL_TO_SEVERITY[level] ?? SeverityNumber.INFO,
          severityText: level,
          body: typeof record.message === 'string' ? record.message : line,
          timestamp: typeof record.timestamp === 'string' ? new Date(record.timestamp) : undefined,
          attributes: otelLogAttributes(record),
        });
      } catch {
        // Fail-safe: the export bridge must never break local logging.
      }
    },
    flushSync: dest.flushSync?.bind(dest),
  };
}

export interface BuildLoggerOptions {
  /** Extra fast-redact paths appended to DEFAULT_REDACT_PATHS. */
  redactPaths?: string[];
  /** Opt this logger out of the OTel Logs bridge (default: bridged). */
  telemetryBridge?: boolean;
  /** Destination override (tests); default: async stdout (SonicBoom). */
  destination?: LogDestination;
}

/** Build a contract-conformant pino logger (redaction + bridge + async sink). */
export function buildLogger(options: BuildLoggerOptions = {}): pino.Logger {
  const dest = options.destination ?? (pino.destination({ sync: false }) as LogDestination);
  registerSink(dest);
  const tee = createTeeStream(dest, { bridge: options.telemetryBridge ?? true });
  return pino(
    {
      level: process.env.LOG_LEVEL ?? 'info',
      base: { service: SERVICE, origin: ORIGIN },
      messageKey: 'message',
      // ISO-8601 timestamp under the `timestamp` key.
      timestamp: () => `,"timestamp":"${new Date().toISOString()}"`,
      formatters: {
        // Emit the textual level name ("info") instead of a numeric value.
        level(label) {
          return { level: label };
        },
      },
      redact: {
        paths: [...DEFAULT_REDACT_PATHS, ...(options.redactPaths ?? [])],
        censor: REDACTION_CENSOR,
      },
    },
    tee as pino.DestinationStream,
  );
}

const baseLogger = buildLogger();

export type LogLevel = 'trace' | 'debug' | 'info' | 'warn' | 'error' | 'fatal';

/**
 * Emit a structured log line. `env` and `trace_id` are attached on every call;
 * `trace_id` is read from the request-scoped async-local store (falls back to
 * "none" when logging outside a request scope).
 */
export function log(level: LogLevel, message: string, extra?: Record<string, unknown>): void {
  baseLogger[level](
    {
      env: process.env.APP_ENV ?? 'local',
      trace_id: getTraceId() ?? 'none',
      ...extra,
    },
    message,
  );
}

export const logger = baseLogger;
