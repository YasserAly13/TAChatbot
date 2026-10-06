import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mockRecordServerDuration = vi.fn();
const mockRecordHopDuration = vi.fn();
const mockRecordUpstreamFailure = vi.fn();
vi.mock('@/lib/metrics', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./metrics')>();
  return {
    ...actual,
    recordServerDuration: (...args: unknown[]) => mockRecordServerDuration(...args),
    recordHopDuration: (...args: unknown[]) => mockRecordHopDuration(...args),
    recordUpstreamFailure: (...args: unknown[]) => mockRecordUpstreamFailure(...args),
  };
});

import {
  ORIGIN,
  TRACE_HEADER,
  TRACE_ID_REGEX,
  envHex,
  fetchUpstream,
  generateTraceId,
  getTraceId,
  isValidTraceId,
  resolveInboundTraceId,
  withBff,
} from './trace';

describe('web trace lib', () => {
  beforeEach(() => {
    mockRecordServerDuration.mockReset();
    mockRecordHopDuration.mockReset();
    mockRecordUpstreamFailure.mockReset();
  });
  afterEach(() => vi.restoreAllMocks());

  describe('envHex', () => {
    it.each([
      ['local', '0'],
      ['dev', '1'],
      ['staging', '2'],
      ['prod', '3'],
      ['sandbox', '4'],
    ])('maps %s -> %s', (e, h) => {
      expect(envHex(e)).toBe(h);
    });
    it('treats unknown/missing as local (0)', () => {
      expect(envHex('nope')).toBe('0');
      expect(envHex()).toBe('0');
    });
  });

  describe('generateTraceId', () => {
    it('is 32 hex chars with the web origin 0eb0', () => {
      const id = generateTraceId();
      expect(id).toMatch(TRACE_ID_REGEX);
      expect(id).toHaveLength(32);
      expect(id.startsWith(ORIGIN)).toBe(true);
    });
  });

  describe('isValidTraceId', () => {
    it('accepts 32 hex and rejects junk/nullish', () => {
      expect(isValidTraceId(`0eb00${'a'.repeat(27)}`)).toBe(true);
      expect(isValidTraceId('nope')).toBe(false);
      expect(isValidTraceId(null)).toBe(false);
      expect(isValidTraceId(undefined)).toBe(false);
    });
  });

  describe('resolveInboundTraceId', () => {
    it('adopts a valid inbound x-trace-id', () => {
      const id = `0c700${'a'.repeat(27)}`;
      const req = new Request('http://web/', { headers: { [TRACE_HEADER]: id } });
      expect(resolveInboundTraceId(req)).toBe(id);
    });
    it('mints a web-origin id when the header is missing or invalid', () => {
      expect(resolveInboundTraceId(new Request('http://web/'))).toMatch(/^0eb0[0-9a-f]{28}$/);
      const bad = new Request('http://web/', { headers: { [TRACE_HEADER]: 'bad' } });
      expect(resolveInboundTraceId(bad)).toMatch(/^0eb0[0-9a-f]{28}$/);
    });
  });

  describe('withBff', () => {
    it('runs the handler inside the trace scope and echoes x-trace-id', async () => {
      let seen: string | undefined;
      const res = await withBff(new Request('http://web/'), ({ traceId }) => {
        seen = getTraceId();
        expect(seen).toBe(traceId);
        return Response.json({ ok: true });
      });
      const echoed = res.headers.get(TRACE_HEADER);
      expect(echoed).toMatch(/^0eb0[0-9a-f]{28}$/);
      expect(echoed).toBe(seen);
    });

    it('adopts and echoes a valid inbound id', async () => {
      const id = `0c700${'b'.repeat(27)}`;
      const res = await withBff(
        new Request('http://web/', { headers: { [TRACE_HEADER]: id } }),
        () => Response.json({}),
      );
      expect(res.headers.get(TRACE_HEADER)).toBe(id);
    });

    it('records the request-duration metric with the pathname as route_class', async () => {
      await withBff(new Request('http://web/api/ping-backend'), () =>
        Response.json({}, { status: 200 }),
      );
      expect(mockRecordServerDuration).toHaveBeenCalledWith(
        expect.objectContaining({
          routeClass: '/api/ping-backend',
          method: 'GET',
          statusCode: 200,
        }),
      );
    });

    it('honors an explicit routeClass option (dynamic segments stay bounded)', async () => {
      await withBff(
        new Request('http://web/api/v1/things/42'),
        () => Response.json({}, { status: 200 }),
        { routeClass: '/api/v1/things/[id]' },
      );
      expect(mockRecordServerDuration).toHaveBeenCalledWith(
        expect.objectContaining({ routeClass: '/api/v1/things/[id]' }),
      );
    });

    it('records a 500 sample and rethrows when the handler throws', async () => {
      await expect(
        withBff(new Request('http://web/api/boom'), () => {
          throw new Error('handler boom');
        }),
      ).rejects.toThrow('handler boom');
      expect(mockRecordServerDuration).toHaveBeenCalledWith(
        expect.objectContaining({ routeClass: '/api/boom', statusCode: 500 }),
      );
    });
  });

  describe('fetchUpstream', () => {
    const ID = `0eb00${'c'.repeat(27)}`;
    const ORIGINAL_API_BASE_URL = process.env.API_BASE_URL;

    beforeEach(() => {
      process.env.API_BASE_URL = 'http://up';
    });
    afterEach(() => {
      if (ORIGINAL_API_BASE_URL === undefined) delete process.env.API_BASE_URL;
      else process.env.API_BASE_URL = ORIGINAL_API_BASE_URL;
    });

    it('forwards the current x-trace-id to the upstream call', async () => {
      const spy = vi
        .spyOn(globalThis, 'fetch')
        .mockResolvedValue(new Response('{}', { status: 200 }));
      await fetchUpstream('http://up/ping', ID);
      expect(spy).toHaveBeenCalledTimes(1);
      const [url, init] = spy.mock.calls[0];
      expect(url).toBe('http://up/ping');
      expect(new Headers(init?.headers).get(TRACE_HEADER)).toBe(ID);
    });

    it('bounds every call with a timeout signal by default', async () => {
      const spy = vi
        .spyOn(globalThis, 'fetch')
        .mockResolvedValue(new Response('{}', { status: 200 }));
      await fetchUpstream('http://up/ping', ID);
      const init = spy.mock.calls[0][1];
      expect(init?.signal).toBeInstanceOf(AbortSignal);
      expect(init?.signal?.aborted).toBe(false);
    });

    it('keeps a caller-supplied signal instead of the default timeout', async () => {
      const spy = vi
        .spyOn(globalThis, 'fetch')
        .mockResolvedValue(new Response('{}', { status: 200 }));
      const controller = new AbortController();
      await fetchUpstream('http://up/ping', ID, { signal: controller.signal });
      expect(spy.mock.calls[0][1]?.signal).toBe(controller.signal);
    });

    it('surfaces an aborted (timed-out) call as a network_error', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValue(
        new DOMException('The operation was aborted due to timeout', 'TimeoutError'),
      );
      await expect(fetchUpstream('http://up/ping', ID)).rejects.toThrow(/timeout/i);
      expect(mockRecordUpstreamFailure).toHaveBeenCalledWith('api', 'network_error');
    });

    it('records the hop metric with a bounded target and status-class outcome', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200 }));
      await fetchUpstream('http://up/ping', ID);
      expect(mockRecordHopDuration).toHaveBeenCalledWith(
        expect.objectContaining({ target: 'api', outcome: '2xx' }),
      );
      expect(mockRecordUpstreamFailure).not.toHaveBeenCalled();
    });

    it('counts a 5xx upstream response as an http_5xx failure', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('oops', { status: 503 }));
      const res = await fetchUpstream('http://up/ping', ID);
      expect(res.status).toBe(503);
      expect(mockRecordHopDuration).toHaveBeenCalledWith(
        expect.objectContaining({ target: 'api', outcome: '5xx' }),
      );
      expect(mockRecordUpstreamFailure).toHaveBeenCalledWith('api', 'http_5xx');
    });

    it('counts a network error as network_error and rethrows', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('ECONNREFUSED'));
      await expect(fetchUpstream('http://up/ping', ID)).rejects.toThrow('ECONNREFUSED');
      expect(mockRecordHopDuration).toHaveBeenCalledWith(
        expect.objectContaining({ target: 'api', outcome: 'error' }),
      );
      expect(mockRecordUpstreamFailure).toHaveBeenCalledWith('api', 'network_error');
    });
  });
});
