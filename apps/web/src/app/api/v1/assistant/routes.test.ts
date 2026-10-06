import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { POST as ask } from '@/app/api/v1/assistant/ask/route';
import { POST as askStream } from '@/app/api/v1/assistant/ask/stream/route';
import { MOCK_HEADER } from '@/lib/mocks';
import { TRACE_HEADER } from '@/lib/trace';
import { askFixture } from '@/mocks/assistant';

function post(path: string, body: unknown, headers: Record<string, string> = {}) {
  return new Request(`http://web${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...headers },
    body: JSON.stringify(body),
  });
}

describe('assistant BFF routes (/api/v1/assistant/ask[/stream])', () => {
  beforeEach(() => {
    process.env.API_BASE_URL = 'http://api:8000';
    delete process.env.MOCK_UPSTREAM;
  });
  afterEach(() => {
    vi.restoreAllMocks();
    delete process.env.MOCK_UPSTREAM;
  });

  it('rejects an empty question with 400 + trace_id', async () => {
    const res = await ask(post('/api/v1/assistant/ask', { question: '  ' }));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toBe('invalid_request');
    expect(body.trace_id).toMatch(/^0eb0[0-9a-f]{28}$/);
  });

  it('serves the fixture in mock mode, marked as a mock', async () => {
    process.env.MOCK_UPSTREAM = 'true';
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const res = await ask(post('/api/v1/assistant/ask', { question: 'hi' }));
    expect(res.status).toBe(200);
    expect(res.headers.get(MOCK_HEADER)).toBe('true');
    await expect(res.json()).resolves.toEqual(askFixture);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('proxies to api /v1/assistant/ask with POST, the same x-trace-id and a long timeout', async () => {
    const inbound = `0eb00${'d'.repeat(27)}`;
    const spy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(Response.json({ answer: 'real', sources: [] }));
    const res = await ask(
      post('/api/v1/assistant/ask', { question: 'hi' }, { [TRACE_HEADER]: inbound }),
    );
    expect(res.status).toBe(200);
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe('http://api:8000/v1/assistant/ask');
    expect(init?.method).toBe('POST');
    expect(new Headers(init?.headers).get(TRACE_HEADER)).toBe(inbound);
    expect(init?.signal).toBeInstanceOf(AbortSignal);
    expect(res.headers.get(TRACE_HEADER)).toBe(inbound);
  });

  it('returns 502 with trace_id when the api is unreachable', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('ECONNREFUSED'));
    const res = await ask(post('/api/v1/assistant/ask', { question: 'hi' }));
    expect(res.status).toBe(502);
    expect((await res.json()).error).toBe('upstream_unreachable');
  });

  it('stream route serves paced fixture frames in mock mode', async () => {
    process.env.MOCK_UPSTREAM = 'true';
    const res = await askStream(post('/api/v1/assistant/ask/stream', { question: 'hi' }));
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toContain('text/event-stream');
    expect(res.headers.get(MOCK_HEADER)).toBe('true');
    const text = await res.text();
    expect(text.startsWith('event: sources')).toBe(true);
    expect(text).toContain('event: done');
  });

  it('stream route proxies the upstream SSE body and headers', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('event: done\ndata: {}\n\n', {
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
      }),
    );
    const res = await askStream(post('/api/v1/assistant/ask/stream', { question: 'hi' }));
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toContain('text/event-stream');
    expect(res.headers.get(TRACE_HEADER)).toMatch(/^0eb0[0-9a-f]{28}$/);
    await expect(res.text()).resolves.toBe('event: done\ndata: {}\n\n');
  });

  it('stream route turns an unreachable api into a terminal SSE error frame', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('ECONNREFUSED'));
    const res = await askStream(post('/api/v1/assistant/ask/stream', { question: 'hi' }));
    expect(res.status).toBe(502);
    await expect(res.text()).resolves.toContain('"error_kind":"upstream_unreachable"');
  });

  it('stream route returns 502 JSON when the api rejects the stream', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('nope', { status: 404 }));
    const res = await askStream(post('/api/v1/assistant/ask/stream', { question: 'hi' }));
    expect(res.status).toBe(502);
    expect((await res.json()).error).toBe('upstream_error');
  });
});
