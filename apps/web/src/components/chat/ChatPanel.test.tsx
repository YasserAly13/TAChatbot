// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { sseFrame, sseStreamFromFrames } from '@/lib/sse';
import { ChatPanel } from './ChatPanel';

describe('<ChatPanel />', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('streams an answer into the thread and shows its sources', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        sseStreamFromFrames([
          sseFrame('sources', { sources: ['docs/api.md'], count: 1 }),
          sseFrame('token', { text: 'Port ' }),
          sseFrame('token', { text: '8000' }),
          sseFrame('done', { sources: ['docs/api.md'] }),
        ]),
        { status: 200, headers: { 'content-type': 'text/event-stream' } },
      ),
    );
    const user = userEvent.setup();
    render(<ChatPanel endpoint="/api/v1/assistant/ask/stream" />);

    await user.type(screen.getByLabelText('Message'), 'which port?{Enter}');

    await waitFor(() => expect(screen.getByText('Port 8000')).toBeInTheDocument());
    expect(screen.getByText('which port?')).toBeInTheDocument();
    expect(screen.getByLabelText('Sources')).toHaveTextContent('docs/api.md');
    await waitFor(() => expect(screen.queryByLabelText('Streaming')).not.toBeInTheDocument());
    const [url] = (globalThis.fetch as unknown as { mock: { calls: [string][] } }).mock.calls[0];
    expect(url).toBe('/api/v1/assistant/ask/stream'); // same-origin only
  });

  it('surfaces a bounded error on failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('x', { status: 502 }));
    const user = userEvent.setup();
    render(<ChatPanel endpoint="/api/v1/assistant/ask/stream" />);
    await user.type(screen.getByLabelText('Message'), 'q{Enter}');
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('upstream_error'));
  });
});
