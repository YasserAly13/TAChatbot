import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { MOCK_HEADER, isMockUpstream, mockJson, mockSse } from '@/lib/mocks';
import { sseFrame } from '@/lib/sse';
import { TRACE_HEADER } from '@/lib/trace';

const TRACE = `0eb00${'c'.repeat(27)}`;

describe('mock upstream mode', () => {
  beforeEach(() => {
    delete process.env.MOCK_UPSTREAM;
    delete process.env.APP_ENV;
  });
  afterEach(() => {
    delete process.env.MOCK_UPSTREAM;
    delete process.env.APP_ENV;
  });

  it('is off unless MOCK_UPSTREAM=true, and always off in prod', () => {
    expect(isMockUpstream()).toBe(false);
    process.env.MOCK_UPSTREAM = 'true';
    expect(isMockUpstream()).toBe(true);
    process.env.APP_ENV = 'prod';
    expect(isMockUpstream()).toBe(false);
  });

  it('mockJson marks the response and echoes the trace id', async () => {
    const res = mockJson({ ok: true }, TRACE, 201);
    expect(res.status).toBe(201);
    expect(res.headers.get(MOCK_HEADER)).toBe('true');
    expect(res.headers.get(TRACE_HEADER)).toBe(TRACE);
    await expect(res.json()).resolves.toEqual({ ok: true });
  });

  it('mockSse streams the frames as text/event-stream', async () => {
    const res = mockSse([sseFrame('token', { text: 'a' }), sseFrame('done', {})], TRACE, 0);
    expect(res.headers.get('content-type')).toContain('text/event-stream');
    expect(res.headers.get(MOCK_HEADER)).toBe('true');
    const text = await res.text();
    expect(text).toBe('event: token\ndata: {"text":"a"}\n\nevent: done\ndata: {}\n\n');
  });
});
