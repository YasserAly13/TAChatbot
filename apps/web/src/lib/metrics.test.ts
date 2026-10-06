/**
 * Custom-metric helper tests (Phase 3, offline):
 *   - namespaced meters ("ai-accelerator.<scope>") from the global provider
 *   - bounded status classes / upstream-target labels
 *   - starter instruments record with bounded attributes only
 *   - recording is best-effort: a throwing provider never breaks the caller
 */
import { metrics } from '@opentelemetry/api';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import {
  __resetMetricsForTests,
  getMeter,
  recordHopDuration,
  recordServerDuration,
  recordUpstreamFailure,
  resolveTarget,
  statusClass,
} from './metrics';

interface Recorded {
  instrument: string;
  value: number;
  attributes: Record<string, unknown>;
}

const recorded: Recorded[] = [];
let throwOnRecord = false;
const meterNames: string[] = [];

const fakeMeter = {
  createHistogram: (name: string) => ({
    record: (value: number, attributes: Record<string, unknown>) => {
      if (throwOnRecord) throw new Error('meter boom');
      recorded.push({ instrument: name, value, attributes });
    },
  }),
  createCounter: (name: string) => ({
    add: (value: number, attributes: Record<string, unknown>) => {
      if (throwOnRecord) throw new Error('meter boom');
      recorded.push({ instrument: name, value, attributes });
    },
  }),
};

const fakeProvider = {
  getMeter: (name: string) => {
    meterNames.push(name);
    return fakeMeter;
  },
};

beforeAll(() => {
  metrics.setGlobalMeterProvider(fakeProvider as never);
});

afterAll(() => {
  metrics.disable();
});

beforeEach(() => {
  recorded.length = 0;
  meterNames.length = 0;
  throwOnRecord = false;
  __resetMetricsForTests();
});

describe('getMeter', () => {
  it('namespaces meters as ai-accelerator.<scope>', () => {
    getMeter('billing');
    expect(meterNames).toContain('ai-accelerator.billing');
  });
});

describe('statusClass', () => {
  it.each([
    [200, '2xx'],
    [301, '3xx'],
    [404, '4xx'],
    [502, '5xx'],
  ])('maps %i to %s', (status, expected) => {
    expect(statusClass(status)).toBe(expected);
  });

  it.each([0, 99, 600, NaN, 3.5])('collapses out-of-range %d to "unknown"', (status) => {
    expect(statusClass(status)).toBe('unknown');
  });
});

describe('resolveTarget', () => {
  // Next's types make NODE_ENV required on ProcessEnv.
  const env = {
    API_BASE_URL: 'http://localhost:8000',
    NODE_ENV: 'test',
  } as NodeJS.ProcessEnv;

  it('labels the api upstream by origin', () => {
    expect(resolveTarget('http://localhost:8000/ping', env)).toBe('api');
  });

  it('collapses a different port on the same host to "other"', () => {
    expect(resolveTarget('http://localhost:9999/ping', env)).toBe('other');
  });

  it('collapses unknown hosts to "other" (bounded cardinality)', () => {
    expect(resolveTarget('https://example.com/x', env)).toBe('other');
  });

  it('collapses invalid URLs to "other" instead of throwing', () => {
    expect(resolveTarget('not a url', env)).toBe('other');
  });
});

describe('recordServerDuration', () => {
  it('records on the server histogram with bounded attributes', () => {
    recordServerDuration({
      routeClass: '/api/ping-backend',
      method: 'GET',
      statusCode: 200,
      durationMs: 12,
    });
    expect(recorded).toEqual([
      {
        instrument: 'ai-accelerator.http.server.duration',
        value: 12,
        attributes: { route_class: '/api/ping-backend', method: 'GET', status_class: '2xx' },
      },
    ]);
  });

  it('never throws when the provider throws', () => {
    throwOnRecord = true;
    expect(() =>
      recordServerDuration({ routeClass: '/x', method: 'GET', statusCode: 200, durationMs: 1 }),
    ).not.toThrow();
  });
});

describe('recordHopDuration', () => {
  it('records on the hop histogram with target and outcome', () => {
    recordHopDuration({ target: 'api', outcome: '2xx', durationMs: 5 });
    expect(recorded).toEqual([
      {
        instrument: 'ai-accelerator.http.client.hop.duration',
        value: 5,
        attributes: { target: 'api', outcome: '2xx' },
      },
    ]);
  });
});

describe('recordUpstreamFailure', () => {
  it('counts one failure with target and reason', () => {
    recordUpstreamFailure('api', 'http_5xx');
    expect(recorded).toEqual([
      {
        instrument: 'ai-accelerator.bff.upstream.failures',
        value: 1,
        attributes: { target: 'api', reason: 'http_5xx' },
      },
    ]);
  });

  it('never throws when the provider throws', () => {
    throwOnRecord = true;
    expect(() => recordUpstreamFailure('api', 'network_error')).not.toThrow();
  });
});
