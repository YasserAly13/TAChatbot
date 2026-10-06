import { ChatPanel } from '@/components/chat/ChatPanel';

/**
 * Example chat page on the UI foundation (ADR-0010). It talks only to the same-origin BFF
 * route `/api/v1/assistant/ask/stream`; with `MOCK_UPSTREAM=true` that route streams the
 * fixture in `src/mocks/assistant.ts`, otherwise it proxies the api's `/v1/assistant/ask/stream`
 * (which a project adds on `app/ai/` — the template ships none).
 */
export default function ChatPage() {
  return (
    <main className="px-4 py-8">
      <ChatPanel endpoint="/api/v1/assistant/ask/stream" title="Assistant (example)" />
      <p className="mx-auto mt-4 max-w-3xl text-xs text-neutral-500">
        Set <code>MOCK_UPSTREAM=true</code> in <code>apps/web/.env.local</code> to try this page
        before the api route exists.
      </p>
    </main>
  );
}
