/**
 * Custom-event helper tests (Phase 3, offline):
 *   - emits an OTel log record with the microsoft.custom_event.name marker
 *   - degraded mode → no export, local structured line still written
 *   - a throwing exporter never breaks the caller
 */
import { SeverityNumber } from '@opentelemetry/api-logs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mockEmit = vi.fn();
const mockGetObservabilityState = vi.fn((): { enabled: boolean; reason: string } => ({
  enabled: false,
  reason: 'test default',
}));

vi.mock('@/lib/observability', () => ({
  getObservabilityState: () => mockGetObservabilityState(),
}));

vi.mock('@opentelemetry/api-logs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@opentelemetry/api-logs')>();
  return {
    SeverityNumber: actual.SeverityNumber,
    logs: { getLogger: () => ({ emit: mockEmit }) },
  };
});

import { CUSTOM_EVENT_MARKER, __setEventLoggerForTests, trackEvent } from './events';
import { buildLogger, type LogDestination } from './logger';

function memoryDest(): LogDestination & { lines: string[] } {
  const lines: string[] = [];
  return { lines, write: (line: string) => lines.push(line) };
}

let dest: ReturnType<typeof memoryDest>;

beforeEach(() => {
  process.env.LOG_LEVEL = 'info';
  mockEmit.mockReset();
  mockGetObservabilityState.mockReset();
  mockGetObservabilityState.mockReturnValue({ enabled: false, reason: 'test default' });
  dest = memoryDest();
  __setEventLoggerForTests(buildLogger({ telemetryBridge: false, destination: dest }));
});

afterEach(() => {
  __setEventLoggerForTests(undefined);
});

describe('trackEvent', () => {
  it('emits a marker record when observability is enabled', () => {
    mockGetObservabilityState.mockReturnValue({ enabled: true, reason: 'ok' });
    trackEvent('service.start', { mode: 'test' });
    expect(mockEmit).toHaveBeenCalledTimes(1);
    const record = mockEmit.mock.calls[0][0] as {
      body: string;
      severityNumber: number;
      attributes: Record<string, unknown>;
    };
    expect(record.body).toBe('service.start');
    expect(record.severityNumber).toBe(SeverityNumber.INFO);
    expect(record.attributes[CUSTOM_EVENT_MARKER]).toBe('service.start');
    expect(record.attributes.mode).toBe('test');
  });

  it('does not export in degraded mode but still writes the local line', () => {
    trackEvent('service.start');
    expect(mockEmit).not.toHaveBeenCalled();
    expect(dest.lines).toHaveLength(1);
    const line = JSON.parse(dest.lines[0]) as Record<string, unknown>;
    expect(line.event).toBe('service.start');
    expect(line.message).toBe('custom event');
  });

  it('never throws when the exporter throws', () => {
    mockGetObservabilityState.mockReturnValue({ enabled: true, reason: 'ok' });
    mockEmit.mockImplementation(() => {
      throw new Error('exporter boom');
    });
    expect(() => trackEvent('service.start')).not.toThrow();
    expect(dest.lines).toHaveLength(1);
  });
});
