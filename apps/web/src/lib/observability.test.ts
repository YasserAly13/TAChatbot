/**
 * Observability bootstrap tests (offline — @azure/monitor-opentelemetry mocked).
 *
 * Covers the Phase 0 roadmap items:
 *   - fail-safe degraded mode (no connection string / init throws)
 *   - idempotent init (process-global guard, shared across module graphs)
 *   - explicitly pinned fixed-percentage sampling (TRACE_SAMPLING_RATIO,
 *     OTEL_TRACES_SAMPLER* precedence, tracesPerSecond: 0)
 *   - cloud role identity env defaults (never override operator values)
 */
import { hostname } from 'node:os';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  __resetObservabilityForTests,
  applyResourceDefaults,
  getObservabilityState,
  initObservability,
  resolveAuthMode,
  resolveSamplingRatio,
} from './observability';

vi.mock('@azure/identity', () => ({
  ManagedIdentityCredential: class MockManagedIdentityCredential {
    options: unknown;
    constructor(options?: unknown) {
      this.options = options;
    }
  },
}));

const mockUseAzureMonitor = vi.fn();
vi.mock('@azure/monitor-opentelemetry', () => ({
  useAzureMonitor: (...args: unknown[]) => mockUseAzureMonitor(...args),
}));

// The extra instrumentations must never actually register in the test process.
const mockRegisterInstrumentations = vi.fn();
vi.mock('@opentelemetry/instrumentation', () => ({
  registerInstrumentations: (...args: unknown[]) => mockRegisterInstrumentations(...args),
}));
vi.mock('@opentelemetry/instrumentation-undici', () => ({
  UndiciInstrumentation: class UndiciInstrumentation {},
}));
vi.mock('@opentelemetry/instrumentation-runtime-node', () => ({
  RuntimeNodeInstrumentation: class RuntimeNodeInstrumentation {},
}));

const FAKE_CONNECTION_STRING =
  'InstrumentationKey=00000000-0000-0000-0000-000000000000;IngestionEndpoint=https://example.invalid/';

/** Next's types make NODE_ENV required on ProcessEnv; build test envs with it set. */
function testEnv(vars: Record<string, string> = {}): NodeJS.ProcessEnv {
  return { ...vars, NODE_ENV: 'test' } as NodeJS.ProcessEnv;
}

const ENV_KEYS = [
  'APPLICATIONINSIGHTS_CONNECTION_STRING',
  'OTEL_SERVICE_NAME',
  'OTEL_RESOURCE_ATTRIBUTES',
  'OTEL_TRACES_SAMPLER',
  'TRACE_SAMPLING_RATIO',
  'CONTAINER_APP_REPLICA_NAME',
  'HOSTNAME',
  'TELEMETRY_AUTH_MODE',
  'TELEMETRY_MANAGED_IDENTITY_CLIENT_ID',
] as const;
const savedEnv: Partial<Record<(typeof ENV_KEYS)[number], string | undefined>> = {};

beforeEach(() => {
  for (const key of ENV_KEYS) {
    savedEnv[key] = process.env[key];
    delete process.env[key];
  }
  __resetObservabilityForTests();
  mockUseAzureMonitor.mockReset();
  mockRegisterInstrumentations.mockReset();
  vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
});

afterEach(() => {
  for (const key of ENV_KEYS) {
    if (savedEnv[key] === undefined) delete process.env[key];
    else process.env[key] = savedEnv[key];
  }
  __resetObservabilityForTests();
  vi.restoreAllMocks();
});

describe('degraded mode (fail-safe)', () => {
  it('reports disabled with a clear reason when no Azure connection string is set', async () => {
    const state = await initObservability();
    expect(state.enabled).toBe(false);
    expect(state.reason).toMatch(/connection string/i);
    expect(mockUseAzureMonitor).not.toHaveBeenCalled();
  });

  it('derives a consistent state from env when init never ran (separate module graph quirk)', () => {
    const state = getObservabilityState();
    expect(state.enabled).toBe(false);
    expect(state.reason).toMatch(/connection string/i);
  });

  it('swallows an SDK init failure and reports disabled with the error reason', async () => {
    process.env.APPLICATIONINSIGHTS_CONNECTION_STRING = FAKE_CONNECTION_STRING;
    mockUseAzureMonitor.mockImplementation(() => {
      throw new Error('boom');
    });
    const state = await initObservability();
    expect(state.enabled).toBe(false);
    expect(state.reason).toContain('boom');
  });
});

describe('ingestion auth mode (Phase 4 hardening)', () => {
  interface ExporterOptions {
    azureMonitorExporterOptions: {
      credential?: { constructor: { name: string }; options?: { clientId?: string } };
    };
  }

  it('defaults to connection-string ingestion with no credential', async () => {
    process.env.APPLICATIONINSIGHTS_CONNECTION_STRING = FAKE_CONNECTION_STRING;
    await initObservability();
    const args = mockUseAzureMonitor.mock.calls[0][0] as ExporterOptions;
    expect(args.azureMonitorExporterOptions.credential).toBeUndefined();
  });

  it('disables observability VISIBLY on a mistyped TELEMETRY_AUTH_MODE (no silent fallback)', async () => {
    process.env.APPLICATIONINSIGHTS_CONNECTION_STRING = FAKE_CONNECTION_STRING;
    process.env.TELEMETRY_AUTH_MODE = 'managed-identity'; // typo: dash, not underscore
    const state = await initObservability();
    expect(state.enabled).toBe(false);
    expect(state.reason).toContain('TELEMETRY_AUTH_MODE');
    expect(mockUseAzureMonitor).not.toHaveBeenCalled();
  });

  it('passes a ManagedIdentityCredential when TELEMETRY_AUTH_MODE=managed_identity', async () => {
    process.env.APPLICATIONINSIGHTS_CONNECTION_STRING = FAKE_CONNECTION_STRING;
    process.env.TELEMETRY_AUTH_MODE = 'managed_identity';
    const state = await initObservability();
    expect(state.enabled).toBe(true);
    const args = mockUseAzureMonitor.mock.calls[0][0] as ExporterOptions;
    const credential = args.azureMonitorExporterOptions.credential;
    expect(credential?.constructor.name).toBe('MockManagedIdentityCredential');
    expect(credential?.options).toBeUndefined(); // system-assigned: no client id
  });

  it('forwards TELEMETRY_MANAGED_IDENTITY_CLIENT_ID for a user-assigned identity', async () => {
    process.env.APPLICATIONINSIGHTS_CONNECTION_STRING = FAKE_CONNECTION_STRING;
    process.env.TELEMETRY_AUTH_MODE = 'managed_identity';
    process.env.TELEMETRY_MANAGED_IDENTITY_CLIENT_ID = 'client-123';
    await initObservability();
    const args = mockUseAzureMonitor.mock.calls[0][0] as ExporterOptions;
    expect(args.azureMonitorExporterOptions.credential?.options).toEqual({
      clientId: 'client-123',
    });
  });

  it('resolveAuthMode accepts the explicit default and rejects junk', () => {
    expect(resolveAuthMode(testEnv({ TELEMETRY_AUTH_MODE: 'connection_string' }))).toEqual({
      mode: 'connection_string',
    });
    expect(resolveAuthMode(testEnv())).toEqual({ mode: 'connection_string' });
    expect(resolveAuthMode(testEnv({ TELEMETRY_AUTH_MODE: 'aad' }))).toHaveProperty('error');
  });
});

describe('extra instrumentations (undici + runtime-node, Phase 2/3)', () => {
  it('registers the undici and runtime-node instrumentations on successful init', async () => {
    process.env.APPLICATIONINSIGHTS_CONNECTION_STRING = FAKE_CONNECTION_STRING;
    await initObservability();
    expect(mockRegisterInstrumentations).toHaveBeenCalledTimes(1);
    const arg = mockRegisterInstrumentations.mock.calls[0][0] as {
      instrumentations: object[];
    };
    const names = arg.instrumentations.map((i) => i.constructor.name);
    expect(names).toEqual(['UndiciInstrumentation', 'RuntimeNodeInstrumentation']);
  });

  it('does not register instrumentations in degraded mode', async () => {
    await initObservability();
    expect(mockRegisterInstrumentations).not.toHaveBeenCalled();
  });

  it('does not register instrumentations when SDK init throws', async () => {
    process.env.APPLICATIONINSIGHTS_CONNECTION_STRING = FAKE_CONNECTION_STRING;
    mockUseAzureMonitor.mockImplementation(() => {
      throw new Error('boom');
    });
    await initObservability();
    expect(mockRegisterInstrumentations).not.toHaveBeenCalled();
  });
});

describe('idempotent init (process-global guard)', () => {
  it('initializes the SDK exactly once across repeated calls', async () => {
    process.env.APPLICATIONINSIGHTS_CONNECTION_STRING = FAKE_CONNECTION_STRING;
    await initObservability();
    await initObservability();
    await initObservability();
    expect(mockUseAzureMonitor).toHaveBeenCalledTimes(1);
    expect(getObservabilityState().enabled).toBe(true);
  });

  it('keeps the degraded state on a second call in degraded mode', async () => {
    await initObservability();
    const state = await initObservability();
    expect(state.enabled).toBe(false);
    expect(mockUseAzureMonitor).not.toHaveBeenCalled();
  });
});

describe('pinned sampling', () => {
  it('pins fixed-percentage sampling at 100% by default (tracesPerSecond 0)', async () => {
    process.env.APPLICATIONINSIGHTS_CONNECTION_STRING = FAKE_CONNECTION_STRING;
    await initObservability();
    expect(mockUseAzureMonitor).toHaveBeenCalledWith(
      expect.objectContaining({ samplingRatio: 1, tracesPerSecond: 0 }),
    );
  });

  it('honors TRACE_SAMPLING_RATIO', async () => {
    process.env.APPLICATIONINSIGHTS_CONNECTION_STRING = FAKE_CONNECTION_STRING;
    process.env.TRACE_SAMPLING_RATIO = '0.25';
    await initObservability();
    expect(mockUseAzureMonitor).toHaveBeenCalledWith(
      expect.objectContaining({ samplingRatio: 0.25, tracesPerSecond: 0 }),
    );
  });

  it.each(['not-a-number', '-0.5', '1.5', 'NaN'])(
    'falls back to 1.0 with a warning on invalid TRACE_SAMPLING_RATIO %s',
    (raw) => {
      const result = resolveSamplingRatio(testEnv({ TRACE_SAMPLING_RATIO: raw }));
      expect(result).toEqual({ ratio: 1, source: 'default' });
      expect(process.stderr.write).toHaveBeenCalledWith(
        expect.stringContaining('TRACE_SAMPLING_RATIO'),
      );
    },
  );

  it('treats empty/missing TRACE_SAMPLING_RATIO as 1.0 without warning', () => {
    expect(resolveSamplingRatio(testEnv({}))).toEqual({ ratio: 1, source: 'default' });
    expect(resolveSamplingRatio(testEnv({ TRACE_SAMPLING_RATIO: '  ' }))).toEqual({
      ratio: 1,
      source: 'default',
    });
  });

  it('accepts boundary values 0 and 1', () => {
    expect(resolveSamplingRatio(testEnv({ TRACE_SAMPLING_RATIO: '0' })).ratio).toBe(0);
    expect(resolveSamplingRatio(testEnv({ TRACE_SAMPLING_RATIO: '1' })).ratio).toBe(1);
  });

  it('defers to the standard OTEL_TRACES_SAMPLER env config when set', () => {
    const result = resolveSamplingRatio(
      testEnv({
        OTEL_TRACES_SAMPLER: 'microsoft.fixed_percentage',
        TRACE_SAMPLING_RATIO: '0.5',
      }),
    );
    expect(result.source).toBe('OTEL_TRACES_SAMPLER');
  });
});

describe('cloud role identity (resource env defaults)', () => {
  it('defaults OTEL_SERVICE_NAME when unset', () => {
    const env = testEnv({});
    applyResourceDefaults(env);
    expect(env.OTEL_SERVICE_NAME).toBe('team-assistant-web');
  });

  it('never overrides an operator-provided OTEL_SERVICE_NAME', () => {
    const env = testEnv({ OTEL_SERVICE_NAME: 'my-renamed-web' });
    applyResourceDefaults(env);
    expect(env.OTEL_SERVICE_NAME).toBe('my-renamed-web');
  });

  it('does not set OTEL_SERVICE_NAME when service.name is already in OTEL_RESOURCE_ATTRIBUTES', () => {
    const env = testEnv({
      OTEL_RESOURCE_ATTRIBUTES: 'service.name=operator-web,service.instance.id=replica-1',
    });
    applyResourceDefaults(env);
    expect(env.OTEL_SERVICE_NAME).toBeUndefined();
    expect(env.OTEL_RESOURCE_ATTRIBUTES).toBe(
      'service.name=operator-web,service.instance.id=replica-1',
    );
  });

  it('appends service.instance.id preferring the container replica name', () => {
    const env = testEnv({ CONTAINER_APP_REPLICA_NAME: 'replica-abc' });
    applyResourceDefaults(env);
    expect(env.OTEL_RESOURCE_ATTRIBUTES).toBe('service.instance.id=replica-abc');
  });

  it('falls back to HOSTNAME, then os.hostname()', () => {
    const env1 = testEnv({ HOSTNAME: 'pod-42' });
    applyResourceDefaults(env1);
    expect(env1.OTEL_RESOURCE_ATTRIBUTES).toBe('service.instance.id=pod-42');

    const env2 = testEnv({});
    applyResourceDefaults(env2);
    expect(env2.OTEL_RESOURCE_ATTRIBUTES).toBe(`service.instance.id=${hostname()}`);
  });

  it('appends to existing operator attributes without touching them', () => {
    const env = testEnv({
      OTEL_RESOURCE_ATTRIBUTES: 'cloud.region=westeurope',
      HOSTNAME: 'pod-42',
    });
    applyResourceDefaults(env);
    expect(env.OTEL_RESOURCE_ATTRIBUTES).toBe('cloud.region=westeurope,service.instance.id=pod-42');
  });

  it('respects an operator-provided service.instance.id', () => {
    const env = testEnv({
      OTEL_RESOURCE_ATTRIBUTES: 'service.instance.id=operator-instance',
    });
    applyResourceDefaults(env);
    expect(env.OTEL_RESOURCE_ATTRIBUTES).toBe('service.instance.id=operator-instance');
  });
});
