// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MessageInput } from './MessageInput';

describe('<MessageInput />', () => {
  afterEach(cleanup); // Vitest globals are off, so RTL does not auto-clean between tests

  it('sends trimmed text on Enter and clears; Shift+Enter inserts a newline', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<MessageInput onSubmit={onSubmit} />);
    const box = screen.getByLabelText('Message');

    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    await user.type(box, '  hello  ');
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
    await user.keyboard('{Enter}');
    expect(onSubmit).toHaveBeenCalledWith('hello');
    expect(box).toHaveValue('');

    await user.type(box, 'a{Shift>}{Enter}{/Shift}b');
    expect(box).toHaveValue('a\nb');
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('is inert while disabled', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<MessageInput onSubmit={onSubmit} disabled />);
    const box = screen.getByLabelText('Message');
    expect(box).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Send' }));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
