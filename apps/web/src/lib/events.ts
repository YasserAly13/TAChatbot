import { logs, SeverityNumber } from '@opentelemetry/api-logs';
import type pino from 'pino';
import { buildLogger } from '@/lib/logger';
import { getObservabilityState } from '@/lib/observability';

/**
 * Custom-event helper (Phase 3 — see .claude/rules/60-observability.md).
 *
 * trackEvent(name, attrs) emits an App Insights `customEvents` row: the Azure
 * Monitor exporter maps any OTel log record carrying the
 * `microsoft.custom_event.name` attribute to an event envelope (verified in
 * @azure/monitor-opentelemetry-exporter 1.0.0-beta.42 logUtils). Emitted
 * synchronously inside the request context, so events are request-correlated.
 *
 * Fail-safe: degraded mode → the exported record is skipped (the local
 * structured line below still prints); an emit failure is swallowed.
 *
 * NO IDENTIFYING ATTRIBUTES: event attributes follow the same no-PII and
 * bounded-cardinality rules as metrics — kinds and outcomes, never ids/emails.
 */

export const CUSTOM_EVENT_MARKER = 'microsoft.custom_event.name';
const EVENT_LOGGER_NAME = 'ai-accelerator-web.events';

export type EventAttributes = Record<string, string | number | boolean>;

// Local visibility: events also print as a structured stdout line. The pino
// telemetry bridge is opted OUT for this logger — the marker record below is
// the exported copy; a bridged line would double-export to AppTraces.
let localLogger: pino.Logger | undefined;

function eventLogger(): pino.Logger {
  localLogger ??= buildLogger({ telemetryBridge: false });
  return localLogger;
}

/** Emit a business-milestone custom event (e.g. "service.start", "X.created"). */
export function trackEvent(name: string, attributes: EventAttributes = {}): void {
  try {
    eventLogger().info({ event: name, ...attributes }, 'custom event');
  } catch {
    // Local logging is best-effort here; never block the caller.
  }
  try {
    if (!getObservabilityState().enabled) {
      return;
    }
    logs.getLogger(EVENT_LOGGER_NAME).emit({
      severityNumber: SeverityNumber.INFO,
      severityText: 'info',
      body: name,
      attributes: { [CUSTOM_EVENT_MARKER]: name, ...attributes },
    });
  } catch {
    // Fail-safe: an export problem must never break the caller.
  }
}

/** TEST-ONLY: inject/clear the local logger (avoids stdout noise in tests). */
export function __setEventLoggerForTests(logger: pino.Logger | undefined): void {
  localLogger = logger;
}
