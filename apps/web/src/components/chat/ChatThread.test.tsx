// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ChatThread } from './ChatThread';

describe('<ChatThread />', () => {
  afterEach(cleanup);

  it('shows the empty state', () => {
    render(<ChatThread messages={[]} />);
    expect(screen.getByTestId('chat-empty')).toHaveTextContent('Ask a question');
  });

  it('renders user and assistant turns with sources, pending and error states', () => {
    render(
      <ChatThread
        messages={[
          { id: '1', role: 'user', text: 'Which port?' },
          {
            id: '2',
            role: 'assistant',
            text: 'Port 8000 [1].',
            sources: ['docs/api.md'],
            pending: true,
          },
          { id: '3', role: 'assistant', text: '', error: 'timeout' },
        ]}
      />,
    );
    const items = screen.getAllByRole('listitem').filter((li) => li.hasAttribute('data-role'));
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveAttribute('data-role', 'user');
    expect(screen.getByText('Port 8000 [1].')).toBeInTheDocument();
    expect(screen.getByLabelText('Sources')).toHaveTextContent('[1] docs/api.md');
    expect(screen.getByLabelText('Streaming')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('timeout');
  });
});
