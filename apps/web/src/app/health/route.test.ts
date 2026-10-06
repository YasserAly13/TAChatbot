import { describe, expect, it } from 'vitest';
import { GET } from '@/app/health/route';
import { TRACE_HEADER } from '@/lib/trace';

describe('web /health', () => {
  it('reports ok, service web, degraded observability, and echoes x-trace-id', async () => {
    delete process.env.APPLICATIONINSIGHTS_CONNECTION_STRING;
    const res = await GET(new Request('http://web/health'));
    expect(res.status).toBe(200);
    expect(res.headers.get(TRACE_HEADER)).toMatch(/^0eb0[0-9a-f]{28}$/);
    const body = await res.json();
    expect(body).toMatchObject({ status: 'ok', service: 'web', observability: 'disabled' });
    expect(body.trace_id).toMatch(/^0eb0[0-9a-f]{28}$/);
  });
});
