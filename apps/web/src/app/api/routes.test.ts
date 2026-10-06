import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GET as infoBackend } from '@/app/api/info-backend/route';
import { GET as pingBackend } from '@/app/api/ping-backend/route';
import { TRACE_HEADER } from '@/lib/trace';

function mockFetchOnce(body: unknown, status = 200) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    }),
  );
}

describe('web BFF route handlers (web → api)', () => {
  beforeEach(() => {
    process.env.API_BASE_URL = 'http://api:8000';
  });
  afterEach(() => vi.restoreAllMocks());

  it('ping-backend → api /ping: forwards x-trace-id, returns upstream JSON, echoes header', async () => {
    const upstream = { service: 'api', message: 'hello', trace_id: 'upstream-echo' };
    const spy = mockFetchOnce(upstream);

    const res = await pingBackend(new Request('http://web/api/ping-backend'));

    expect(res.status).toBe(200);
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe('http://api:8000/ping');
    const traceId = res.headers.get(TRACE_HEADER)!;
    expect(traceId).toMatch(/^0eb0[0-9a-f]{28}$/);
    expect(new Headers(init?.headers).get(TRACE_HEADER)).toBe(traceId);
    await expect(res.json()).resolves.toEqual(upstream);
  });

  it('ping-backend adopts a valid inbound x-trace-id and forwards the SAME id upstream', async () => {
    const inbound = `0eb00${'a'.repeat(27)}`;
    const spy = mockFetchOnce({ service: 'api', message: 'hello', trace_id: inbound });

    const res = await pingBackend(
      new Request('http://web/api/ping-backend', { headers: { [TRACE_HEADER]: inbound } }),
    );

    expect(res.headers.get(TRACE_HEADER)).toBe(inbound);
    expect(new Headers(spy.mock.calls[0][1]?.headers).get(TRACE_HEADER)).toBe(inbound);
  });

  it('ping-backend falls back to http://localhost:8000 when API_BASE_URL is unset', async () => {
    delete process.env.API_BASE_URL;
    const spy = mockFetchOnce({ service: 'api', message: 'hello', trace_id: 'x' });
    await pingBackend(new Request('http://web/api/ping-backend'));
    expect(spy.mock.calls[0][0]).toBe('http://localhost:8000/ping');
  });

  it('returns a graceful 502 with a trace_id when the upstream is unreachable', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('ECONNREFUSED'));
    const res = await pingBackend(new Request('http://web/api/ping-backend'));
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body).toMatchObject({ error: 'upstream_unreachable', target: 'api' });
    expect(body.trace_id).toMatch(/^0eb0[0-9a-f]{28}$/);
  });

  it('info-backend → api /info: forwards x-trace-id, returns upstream JSON, echoes header', async () => {
    const upstream = {
      status: 'ok',
      service: 'api',
      version: '0.0.0',
      trace_id: 'upstream-echo',
    };
    const spy = mockFetchOnce(upstream);

    const res = await infoBackend(new Request('http://web/api/info-backend'));

    expect(res.status).toBe(200);
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe('http://api:8000/info');
    const traceId = res.headers.get(TRACE_HEADER)!;
    expect(traceId).toMatch(/^0eb0[0-9a-f]{28}$/);
    expect(new Headers(init?.headers).get(TRACE_HEADER)).toBe(traceId);
    await expect(res.json()).resolves.toEqual(upstream);
  });

  it('info-backend passes a non-2xx upstream status through unchanged', async () => {
    mockFetchOnce({ status: 'degraded', service: 'api', trace_id: 'x' }, 503);
    const res = await infoBackend(new Request('http://web/api/info-backend'));
    expect(res.status).toBe(503);
  });

  it('info-backend returns a graceful 502 with a trace_id when the upstream is unreachable', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('ECONNREFUSED'));
    const res = await infoBackend(new Request('http://web/api/info-backend'));
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body).toMatchObject({ error: 'upstream_unreachable', target: 'api' });
    expect(body.trace_id).toMatch(/^0eb0[0-9a-f]{28}$/);
  });
});
