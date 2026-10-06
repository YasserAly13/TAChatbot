import { describe, expect, it } from 'vitest';
import { parseSseBlock, readSseStream, sseFrame, sseStreamFromFrames } from '@/lib/sse';

async function collect(stream: ReadableStream<Uint8Array>) {
  const out: { event: string; data: string }[] = [];
  for await (const ev of readSseStream(stream)) out.push(ev);
  return out;
}

describe('sse helpers', () => {
  it('sseFrame produces the api wire format', () => {
    expect(sseFrame('token', { text: 'hi' })).toBe('event: token\ndata: {"text":"hi"}\n\n');
  });

  it('parseSseBlock handles event/data, comments, multi-line data and defaults', () => {
    expect(parseSseBlock('event: done\ndata: {"a":1}')).toEqual({ event: 'done', data: '{"a":1}' });
    expect(parseSseBlock(': keep-alive\ndata: x\ndata: y')).toEqual({
      event: 'message',
      data: 'x\ny',
    });
    expect(parseSseBlock('event: only')).toBeNull();
    expect(parseSseBlock('data:no-space')).toEqual({ event: 'message', data: 'no-space' });
  });

  it('readSseStream yields events across chunk boundaries and a trailing block', async () => {
    const encoder = new TextEncoder();
    const text =
      sseFrame('sources', { sources: ['a'] }) +
      sseFrame('token', { text: 'x' }) +
      'event: done\ndata: {}';
    const chunks = [text.slice(0, 13), text.slice(13, 40), text.slice(40)];
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        for (const chunk of chunks) c.enqueue(encoder.encode(chunk));
        c.close();
      },
    });
    const events = await collect(stream);
    expect(events.map((e) => e.event)).toEqual(['sources', 'token', 'done']);
    expect(JSON.parse(events[1].data)).toEqual({ text: 'x' });
  });

  it('sseStreamFromFrames replays frames in order', async () => {
    const events = await collect(sseStreamFromFrames([sseFrame('a', 1), sseFrame('b', 2)]));
    expect(events).toEqual([
      { event: 'a', data: '1' },
      { event: 'b', data: '2' },
    ]);
  });
});
