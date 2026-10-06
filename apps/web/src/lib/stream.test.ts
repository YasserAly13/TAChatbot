import { afterEach, describe, expect, it, vi } from 'vitest';
import { STREAM_TIMEOUT_MS, proxyStream, streamUpstream } from '@/lib/stream';
import { TRACE_HEADER } from '@/lib/trace';

const TRACE = `0eb00${'b'.repeat(27)}`;

describe('streamUpstream / proxyStream', () => {
  afterEach(() => vi.restoreAllMocks());

  it('forwards x-trace-id, asks for text/event-stream and bounds the call', async () => {
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('event: done\ndata: {}\n\n', { status: 200 }));
    const res = await streamUpstream('http://api:8000/v1/x/stream', TRACE, { method: 'POST' });
    expect(res.status).toBe(200);
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe('http://api:8000/v1/x/stream');
    const headers = new Headers(init?.headers);
    expect(headers.get(TRACE_HEADER)).toBe(TRACE);
    expect(headers.get('accept')).toBe('text/event-stream');
    expect(init?.signal).toBeInstanceOf(AbortSignal);
    expect(init?.cache).toBe('no-store');
    expect(STREAM_TIMEOUT_MS).toBeGreaterThan(10_000);
  });

  it('honours a caller-supplied signal and rethrows network failures', async () => {
    const controller = new AbortController();
    const spy = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('ECONNREFUSED'));
    await expect(
      streamUpstream('http://api:8000/v1/x/stream', TRACE, { signal: controller.signal }),
    ).rejects.toThrow('ECONNREFUSED');
    expect(spy.mock.calls[0][1]?.signal).toBe(controller.signal);
  });

  it('proxyStream passes the body through with SSE headers and the trace id', async () => {
    const upstream = new Response('event: token\ndata: {"text":"a"}\n\n', {
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
    });
    const res = proxyStream(upstream, TRACE);
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toBe('text/event-stream');
    expect(res.headers.get('cache-control')).toContain('no-cache');
    expect(res.headers.get('x-accel-buffering')).toBe('no');
    expect(res.headers.get(TRACE_HEADER)).toBe(TRACE);
    await expect(res.text()).resolves.toContain('event: token');
  });
});
