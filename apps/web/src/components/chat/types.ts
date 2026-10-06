export type ChatRole = 'user' | 'assistant';

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  /** Sources the assistant cited (unique, in citation order). */
  sources?: string[];
  /** Still streaming. */
  pending?: boolean;
  /** Bounded error kind from the stream (never raw exception text). */
  error?: string;
}
