'use client';

import { useRef, useState } from 'react';
import { askStream } from '@/lib/chat-client';
import { ChatThread } from './ChatThread';
import { MessageInput } from './MessageInput';
import type { ChatMessage } from './types';

interface Props {
  /** Same-origin SSE route, e.g. `/api/v1/assistant/ask/stream` (the BFF rule: never the api). */
  endpoint: string;
  title?: string;
}

let counter = 0;
const nextId = () => `m${++counter}`;

/** A complete streaming chat surface: thread + input, wired to a BFF SSE route. */
export function ChatPanel({ endpoint, title = 'Assistant' }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  function patchLast(patch: (m: ChatMessage) => ChatMessage) {
    setMessages((prev) => prev.map((m, i) => (i === prev.length - 1 ? patch(m) : m)));
  }

  async function send(question: string) {
    const assistantId = nextId();
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: 'user', text: question },
      { id: assistantId, role: 'assistant', text: '', pending: true },
    ]);
    setBusy(true);
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    await askStream(
      endpoint,
      question,
      {
        onSources: (sources) => patchLast((m) => ({ ...m, sources })),
        onToken: (text) => patchLast((m) => ({ ...m, text: m.text + text })),
        onDone: ({ sources }) =>
          patchLast((m) => ({
            ...m,
            pending: false,
            sources: sources.length ? sources : m.sources,
          })),
        onError: (kind) => patchLast((m) => ({ ...m, pending: false, error: kind })),
      },
      { signal: abortRef.current.signal },
    );
    setBusy(false);
  }

  return (
    <section className="mx-auto flex w-full max-w-3xl flex-col gap-4" aria-label={title}>
      <h1 className="text-xl font-semibold">{title}</h1>
      <div className="min-h-[16rem] rounded-2xl border border-neutral-200 bg-neutral-50 p-4 dark:border-neutral-800 dark:bg-neutral-950">
        <ChatThread messages={messages} />
      </div>
      <MessageInput onSubmit={send} disabled={busy} />
    </section>
  );
}
