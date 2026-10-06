import { describe, expect, it, vi } from 'vitest';
import { askStream } from '@/lib/chat-client';
import { sseFrame, sseStreamFromFrames } from '@/lib/sse';

function sseResponse(frames: string[], status = 200) {
  return new Response(sseStreamFromFrames(frames), {
    status,
    headers: { 'content-type': 'text/event-stream' },
  });
}

function handlers() {
  return {
    onSources: vi.fn(),
    onToken: vi.fn(),
    onDone: vi.fn(),
    onError: vi.fn(),
  };
}

describe('askStream (browser → BFF)', () => {
  it('posts the question and dispatches sources → tokens → done', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(
        sseResponse([
          sseFrame('sources', { sources: ['docs/a.md'], count: 1 }),
          sseFrame('token', { text: 'Hel' }),
          sseFrame('token', { text: 'lo' }),
          sseFrame('done', { sources: ['docs/a.md'], input_tokens: 3, output_tokens: 2 }),
        ]),
      );
    const h = handlers();
    await askStream('/api/v1/assistant/ask/stream', 'hi', h, { fetchImpl });

    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe('/api/v1/assistant/ask/stream');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ question: 'hi' });
    expect(h.onSources).toHaveBeenCalledWith(['docs/a.md']);
    expect(h.onToken.mock.calls.map((c) => c[0]).join('')).toBe('Hello');
    expect(h.onDone).toHaveBeenCalledWith({
      sources: ['docs/a.md'],
      inputTokens: 3,
      outputTokens: 2,
    });
    expect(h.onError).not.toHaveBeenCalled();
  });

  it('maps an error frame, a rejected request and a network failure to bounded kinds', async () => {
    const h1 = handlers();
    await askStream('/x', 'q', h1, {
      fetchImpl: vi
        .fn()
        .mockResolvedValue(sseResponse([sseFrame('error', { error_kind: 'timeout' })])),
    });
    expect(h1.onError).toHaveBeenCalledWith('timeout');

    const h2 = handlers();
    await askStream('/x', 'q', h2, {
      fetchImpl: vi.fn().mockResolvedValue(new Response('nope', { status: 400 })),
    });
    expect(h2.onError).toHaveBeenCalledWith('request_rejected');

    const h3 = handlers();
    await askStream('/x', 'q', h3, { fetchImpl: vi.fn().mockRejectedValue(new Error('down')) });
    expect(h3.onError).toHaveBeenCalledWith('network_error');
  });

  it('skips malformed frames and finishes on stream end without a done frame', async () => {
    const h = handlers();
    await askStream('/x', 'q', h, {
      fetchImpl: vi
        .fn()
        .mockResolvedValue(
          sseResponse(['event: token\ndata: {broken\n\n', sseFrame('token', { text: 'ok' })]),
        ),
    });
    expect(h.onToken).toHaveBeenCalledWith('ok');
    expect(h.onDone).toHaveBeenCalledWith({ sources: [], inputTokens: null, outputTokens: null });
  });
});
