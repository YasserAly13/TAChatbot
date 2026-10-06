/**
 * Log pipeline tests (Phase 1, offline):
 *   - redaction at source (default fields, nesting, extensibility) hits every sink
 *   - OTel Logs bridge: emits when enabled, no-ops when disabled/opted-out,
 *     never breaks local logging on failure
 *   - non-blocking sink flush at exit (best-effort, swallow errors)
 */
import { afterAll, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';

const { mockEmit, mockState } = vi.hoisted(() => ({
  mockEmit: vi.fn(),
  mockState: vi.fn((): { enabled: boolean; reason: string } => ({
    enabled: false,
    reason: 'test default',
  })),
}));

vi.mock('@/lib/observability', () => ({
  getObservabilityState: () => mockState(),
}));

vi.mock('@opentelemetry/api-logs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@opentelemetry/api-logs')>();
  return {
    SeverityNumber: actual.SeverityNumber,
    logs: { getLogger: () => ({ emit: mockEmit }) },
  };
});

import { SeverityNumber } from '@opentelemetry/api-logs';
import {
  DEFAULT_REDACTED_FIELDS,
  REDACTION_CENSOR,
  buildLogger,
  flushAllLogSinks,
  otelLogAttributes,
  type LogDestination,
} from './logger';

function memoryDest(): LogDestination & { lines: string[]; flushSync: Mock<() => void> } {
  const lines: string[] = [];
  return {
    lines,
    write: (line: string) => lines.push(line),
    flushSync: vi.fn<() => void>(),
  };
}

function lastRecord(dest: { lines: string[] }): Record<string, unknown> {
  return JSON.parse(dest.lines[dest.lines.length - 1]) as Record<string, unknown>;
}

const ORIGINAL_LOG_LEVEL = process.env.LOG_LEVEL;

beforeEach(() => {
  process.env.LOG_LEVEL = 'info';
  mockEmit.mockReset();
  mockState.mockReset();
  mockState.mockReturnValue({ enabled: false, reason: 'test default' });
});

afterAll(() => {
  process.env.LOG_LEVEL = ORIGINAL_LOG_LEVEL;
});

describe('redaction at source', () => {
  it.each([...DEFAULT_REDACTED_FIELDS])(
    'censors default field %s at the top level before any sink',
    (field) => {
      const dest = memoryDest();
      const logger = buildLogger({ destination: dest, telemetryBridge: false });
      logger.info({ [field]: 'super-secret-value' }, 'testing redaction');
      expect(lastRecord(dest)[field]).toBe(REDACTION_CENSOR);
      expect(dest.lines[dest.lines.length - 1]).not.toContain('super-secret-value');
    },
  );

  it('censors default fields nested one level deep', () => {
    const dest = memoryDest();
    const logger = buildLogger({ destination: dest, telemetryBridge: false });
    logger.info(
      { headers: { authorization: 'Bearer abc123', 'set-cookie': 'sid=xyz' } },
      'inbound headers',
    );
    const headers = lastRecord(dest).headers as Record<string, unknown>;
    expect(headers.authorization).toBe(REDACTION_CENSOR);
    expect(headers['set-cookie']).toBe(REDACTION_CENSOR);
  });

  it('is extensible per logger via redactPaths', () => {
    const dest = memoryDest();
    const logger = buildLogger({
      destination: dest,
      telemetryBridge: false,
      redactPaths: ['ssn', '*.ssn'],
    });
    logger.info({ ssn: '123-45-6789', person: { ssn: '987' } }, 'custom redaction');
    const record = lastRecord(dest);
    expect(record.ssn).toBe(REDACTION_CENSOR);
    expect((record.person as Record<string, unknown>).ssn).toBe(REDACTION_CENSOR);
  });

  it('leaves non-secret fields intact', () => {
    const dest = memoryDest();
    const logger = buildLogger({ destination: dest, telemetryBridge: false });
    logger.info({ status: 200, url: '/api/ping-backend' }, 'ok');
    const record = lastRecord(dest);
    expect(record.status).toBe(200);
    expect(record.url).toBe('/api/ping-backend');
  });
});

describe('OTel Logs bridge', () => {
  it('emits a bridged record (severity, body, attributes) when observability is enabled', () => {
    mockState.mockReturnValue({ enabled: true, reason: 'ok' });
    const dest = memoryDest();
    const logger = buildLogger({ destination: dest });
    logger.info({ foo: 'bar' }, 'hello export');

    expect(mockEmit).toHaveBeenCalledTimes(1);
    const emitted = mockEmit.mock.calls[0][0];
    expect(emitted.severityText).toBe('info');
    expect(emitted.severityNumber).toBe(SeverityNumber.INFO);
    expect(emitted.body).toBe('hello export');
    expect(emitted.attributes.foo).toBe('bar');
    expect(emitted.attributes.service).toBe('web');
    // level/message/timestamp map to the record itself, not attributes.
    expect(emitted.attributes.level).toBeUndefined();
    expect(emitted.attributes.message).toBeUndefined();
  });

  it('maps warn/error levels to matching severities', () => {
    mockState.mockReturnValue({ enabled: true, reason: 'ok' });
    const dest = memoryDest();
    const logger = buildLogger({ destination: dest });
    logger.warn('warned');
    logger.error('failed');
    expect(mockEmit.mock.calls[0][0].severityNumber).toBe(SeverityNumber.WARN);
    expect(mockEmit.mock.calls[1][0].severityNumber).toBe(SeverityNumber.ERROR);
  });

  it('exports only redacted data (redaction runs before the bridge)', () => {
    mockState.mockReturnValue({ enabled: true, reason: 'ok' });
    const dest = memoryDest();
    const logger = buildLogger({ destination: dest });
    logger.info({ password: 'hunter2' }, 'login attempt');
    expect(mockEmit.mock.calls[0][0].attributes.password).toBe(REDACTION_CENSOR);
  });

  it('is a no-op in degraded mode', () => {
    const dest = memoryDest();
    const logger = buildLogger({ destination: dest });
    logger.info('local only');
    expect(mockEmit).not.toHaveBeenCalled();
    expect(dest.lines).toHaveLength(1);
  });

  it('honors the per-logger opt-out', () => {
    mockState.mockReturnValue({ enabled: true, reason: 'ok' });
    const dest = memoryDest();
    const logger = buildLogger({ destination: dest, telemetryBridge: false });
    logger.info('not bridged');
    expect(mockEmit).not.toHaveBeenCalled();
    expect(dest.lines).toHaveLength(1);
  });

  it('never breaks local logging when the bridge throws', () => {
    mockState.mockReturnValue({ enabled: true, reason: 'ok' });
    mockEmit.mockImplementation(() => {
      throw new Error('exporter exploded');
    });
    const dest = memoryDest();
    const logger = buildLogger({ destination: dest });
    expect(() => logger.info('must still log locally')).not.toThrow();
    expect(dest.lines).toHaveLength(1);
    expect(lastRecord(dest).message).toBe('must still log locally');
  });
});

describe('non-blocking sink flush', () => {
  it('flushAllLogSinks flushes registered destinations synchronously', () => {
    const dest = memoryDest();
    buildLogger({ destination: dest, telemetryBridge: false });
    flushAllLogSinks();
    expect(dest.flushSync).toHaveBeenCalled();
  });

  it('swallows flush errors (best-effort at shutdown)', () => {
    const dest = memoryDest();
    dest.flushSync.mockImplementation(() => {
      throw new Error('fd closed');
    });
    buildLogger({ destination: dest, telemetryBridge: false });
    expect(() => flushAllLogSinks()).not.toThrow();
  });
});

describe('otelLogAttributes', () => {
  it('passes primitives, stringifies objects, drops level/message/timestamp/null', () => {
    const attrs = otelLogAttributes({
      level: 'info',
      message: 'm',
      timestamp: 't',
      count: 3,
      ok: true,
      name: 'x',
      nested: { a: 1 },
      empty: null,
    });
    expect(attrs).toEqual({ count: 3, ok: true, name: 'x', nested: '{"a":1}' });
  });
});
