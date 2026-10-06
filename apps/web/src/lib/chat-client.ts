import { readSseStream } from '@/lib/sse';

/**
 * Browser-side client for a streamed assistant answer (same-origin BFF only — the BFF rule).
 * Framework-free so it is unit-tested in the node environment; components wrap it.
 */
export interface StreamHandlers {
  onSources?: (sources: string[]) => void;
  onToken: (text: string) => void;
  onDone?: (info: {
    sources: string[];
    inputTokens?: number | null;
    outputTokens?: number | null;
  }) => void;
  onError: (errorKind: string) => void;
}

export interface AskStreamOptions {
  signal?: AbortSignal;
  fetchImpl?: typeof fetch;
}

/**
 * POST `{ question }` to a same-origin SSE route and dispatch its events.
 * Resolves when the stream ends; every failure path calls `onError` with a bounded kind.
 */
export async function askStream(
  endpoint: string,
  question: string,
  handlers: StreamHandlers,
  options: AskStreamOptions = {},
): Promise<void> {
  const fetchImpl = options.fetchImpl ?? fetch;
  let res: Response;
  try {
    res = await fetchImpl(endpoint, {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
      body: JSON.stringify({ question }),
      signal: options.signal,
    });
  } catch (err) {
    handlers.onError((err as Error)?.name === 'AbortError' ? 'aborted' : 'network_error');
    return;
  }
  if (!res.ok || !res.body) {
    handlers.onError(res.status >= 500 ? 'upstream_error' : 'request_rejected');
    return;
  }
  let sources: string[] = [];
  try {
    for await (const event of readSseStream(res.body)) {
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(event.data) as Record<string, unknown>;
      } catch {
        continue; // a malformed frame is skipped, never fatal
      }
      switch (event.event) {
        case 'sources':
          sources = Array.isArray(data.sources) ? (data.sources as string[]) : [];
          handlers.onSources?.(sources);
          break;
        case 'token':
          if (typeof data.text === 'string') handlers.onToken(data.text);
          break;
        case 'done':
          handlers.onDone?.({
            sources: Array.isArray(data.sources) ? (data.sources as string[]) : sources,
            inputTokens: (data.input_tokens as number | null | undefined) ?? null,
            outputTokens: (data.output_tokens as number | null | undefined) ?? null,
          });
          return;
        case 'error':
          handlers.onError(typeof data.error_kind === 'string' ? data.error_kind : 'error');
          return;
        default:
          break;
      }
    }
    // Stream ended without a terminal frame.
    handlers.onDone?.({ sources, inputTokens: null, outputTokens: null });
  } catch (err) {
    handlers.onError((err as Error)?.name === 'AbortError' ? 'aborted' : 'stream_error');
  }
}
