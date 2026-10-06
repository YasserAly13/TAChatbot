import type { ChatMessage } from './types';

const ROLE_LABEL: Record<ChatMessage['role'], string> = { user: 'You', assistant: 'Assistant' };

/** The message list. Presentational only — no state, no fetches. */
export function ChatThread({ messages }: Readonly<{ messages: ChatMessage[] }>) {
  if (messages.length === 0) {
    return (
      <p className="text-sm text-neutral-500" data-testid="chat-empty">
        Ask a question to start.
      </p>
    );
  }
  return (
    <ol className="flex flex-col gap-3" aria-live="polite" aria-label="Conversation">
      {messages.map((m) => (
        <li
          key={m.id}
          data-role={m.role}
          className={`max-w-[85%] rounded-xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
            m.role === 'user'
              ? 'self-end bg-blue-600 text-white'
              : 'self-start border border-neutral-200 bg-white text-neutral-900 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100'
          }`}
        >
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wide opacity-70">
            {ROLE_LABEL[m.role]}
          </span>
          <span className="whitespace-pre-wrap">{m.text}</span>
          {m.pending && (
            <span className="ml-1 inline-block animate-pulse" aria-label="Streaming">
              …
            </span>
          )}
          {m.error && (
            <span role="alert" className="mt-2 block text-xs text-red-600">
              Something went wrong ({m.error}). Try again.
            </span>
          )}
          {m.sources && m.sources.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1" aria-label="Sources">
              {m.sources.map((s, i) => (
                <li
                  key={s}
                  className="rounded-md bg-neutral-100 px-2 py-0.5 text-xs text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300"
                >
                  [{i + 1}] {s}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}
