/**
 * Server-Sent Events helpers shared by the BFF (proxying / mocking a stream) and the
 * browser (consuming it). Pure functions + streams — no framework imports, so the parser
 * is unit-tested in the node environment.
 *
 * Wire format (matches apps/api `app/ai/streaming.py`):
 *   event: <name>\n
 *   data: <json>\n
 *   \n
 */

export interface SseEvent {
  event: string;
  data: string;
}

/** Build one SSE frame. `data` is JSON-encoded. */
export function sseFrame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/**
 * Parse one blank-line-delimited block into an event. Comment lines (`:`) are ignored,
 * multiple `data:` lines are joined with `\n`, a block without `event:` is a `message`.
 * Returns null for a block with no data.
 */
export function parseSseBlock(block: string): SseEvent | null {
  let event = 'message';
  const data: string[] = [];
  for (const rawLine of block.split(/\r?\n/)) {
    const line = rawLine.trimEnd();
    if (!line || line.startsWith(':')) continue;
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') event = value;
    else if (field === 'data') data.push(value);
  }
  if (data.length === 0) return null;
  return { event, data: data.join('\n') };
}

/** Iterate the events of an SSE body stream. */
export async function* readSseStream(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<SseEvent, void, undefined> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = parseSseBlock(block);
        if (event) yield event;
        boundary = buffer.indexOf('\n\n');
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) {
      const event = parseSseBlock(buffer);
      if (event) yield event;
    }
  } finally {
    reader.releaseLock();
  }
}

/** A byte stream that emits the given frames (optionally paced) — used by mocks and tests. */
export function sseStreamFromFrames(frames: string[], delayMs = 0): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    async start(controller) {
      for (const frame of frames) {
        if (delayMs > 0) await new Promise((r) => setTimeout(r, delayMs));
        controller.enqueue(encoder.encode(frame));
      }
      controller.close();
    },
  });
}
