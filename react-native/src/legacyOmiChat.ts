import {decodeBase64} from './base64';
import type {ChatHistoryPage, ChatMessage} from './chatClient';

export type OmiChatStreamEvent =
  | {kind: 'data'; text: string}
  | {kind: 'think'; text: string}
  | {kind: 'error'; text: string}
  | {kind: 'done'; message: ChatMessage}
  | {kind: 'message'; message: ChatMessage};

function decodeOmiJson(value: string): unknown {
  return JSON.parse(decodeUtf8(decodeBase64(value.trim())));
}

function decodeUtf8(bytes: Uint8Array): string {
  return decodeURIComponent(
    Array.from(bytes, byte => `%${byte.toString(16).padStart(2, '0')}`).join(
      '',
    ),
  );
}

function fieldValue(line: string, name: string): string | null {
  if (!line.startsWith(`${name}:`)) {
    return null;
  }
  let value = line.slice(name.length + 1);
  if (value.startsWith(' ')) {
    value = value.slice(1);
  }
  return value.replaceAll('__CRLF__', '\n');
}

export function parseOmiChatLine(line: string): OmiChatStreamEvent | null {
  if (line.length === 0 || line.startsWith(':')) {
    return null;
  }
  const data = fieldValue(line, 'data');
  if (data !== null) {
    return {kind: 'data', text: data};
  }
  const think = fieldValue(line, 'think');
  if (think !== null) {
    return {kind: 'think', text: think};
  }
  const error = fieldValue(line, 'error');
  if (error !== null) {
    return {kind: 'error', text: error};
  }
  const done = fieldValue(line, 'done');
  if (done !== null) {
    const message = parseOmiMessage(decodeOmiJson(done));
    if (message.sender !== 'ai') {
      throw new Error('Omi chat terminal sender is invalid');
    }
    return {kind: 'done', message};
  }
  const side = fieldValue(line, 'message');
  if (side !== null) {
    return {kind: 'message', message: parseOmiMessage(decodeOmiJson(side))};
  }
  return null;
}

export class IncrementalOmiChatParser {
  private pendingBytes = new Uint8Array();
  private text = '';

  push(chunk: Uint8Array | string): readonly OmiChatStreamEvent[] {
    if (typeof chunk === 'string') {
      if (this.pendingBytes.length > 0) {
        this.text += decodeUtf8(this.pendingBytes);
        this.pendingBytes = new Uint8Array();
      }
      this.text += chunk;
    } else {
      const bytes = new Uint8Array(this.pendingBytes.length + chunk.length);
      bytes.set(this.pendingBytes);
      bytes.set(chunk, this.pendingBytes.length);
      for (let tail = 0; tail <= Math.min(3, bytes.length); tail += 1) {
        try {
          this.text += decodeUtf8(bytes.subarray(0, bytes.length - tail));
          this.pendingBytes = bytes.slice(bytes.length - tail);
          break;
        } catch {
          if (tail === Math.min(3, bytes.length))
            throw new Error('UTF-8 data is invalid');
        }
      }
    }
    return this.drain(false);
  }

  finish(): readonly OmiChatStreamEvent[] {
    this.text += decodeUtf8(this.pendingBytes);
    this.pendingBytes = new Uint8Array();
    return this.drain(true);
  }

  private drain(finishing: boolean): OmiChatStreamEvent[] {
    this.text = this.text.replaceAll('\r\n', '\n').replaceAll('\r', '\n');
    const events: OmiChatStreamEvent[] = [];
    while (this.text.length > 0) {
      const end = this.text.indexOf('\n\n');
      if (end < 0) {
        if (!finishing) {
          return events;
        }
        this.consumeFrame(this.text, events);
        this.text = '';
        return events;
      }
      this.consumeFrame(this.text.slice(0, end), events);
      this.text = this.text.slice(end + 2);
    }
    return events;
  }

  private consumeFrame(frame: string, events: OmiChatStreamEvent[]): void {
    for (const line of frame.split('\n')) {
      const event = parseOmiChatLine(line);
      if (event !== null) {
        events.push(event);
      }
    }
  }
}

export function parseOmiMessage(value: unknown): ChatMessage {
  if (value === null || typeof value !== 'object') {
    throw new Error('Omi chat message is malformed');
  }
  const row = value as Record<string, unknown>;
  const createdAt =
    typeof row.created_at === 'string' ? Date.parse(row.created_at) : NaN;
  if (
    typeof row.id !== 'string' ||
    row.id.length === 0 ||
    typeof row.text !== 'string' ||
    (row.sender !== 'human' && row.sender !== 'ai') ||
    !Number.isFinite(createdAt)
  ) {
    throw new Error('Omi chat message is malformed');
  }
  return {
    id: row.id,
    text: row.text,
    sender: row.sender,
    createdAt,
    generationOutcome: null,
  };
}

export function omiHistoryOffset(cursor: string): number {
  if (!/^omi-offset:[0-9]+$/.test(cursor)) {
    throw new Error('Omi chat cursor is malformed');
  }
  const offset = Number(cursor.slice('omi-offset:'.length));
  if (!Number.isSafeInteger(offset)) {
    throw new Error('Omi chat cursor is malformed');
  }
  return offset;
}

export function parseOmiHistory(
  body: string | null,
  offset: number,
): ChatHistoryPage {
  const rows: unknown = JSON.parse(body ?? 'null');
  if (!Array.isArray(rows) || rows.length > 50) {
    throw new Error('Omi chat history is malformed');
  }
  return {
    messages: rows.map(parseOmiMessage).reverse(),
    hasOlder: rows.length === 50,
    olderCursor:
      rows.length === 50 ? `omi-offset:${offset + rows.length}` : null,
  };
}

export function parseOmiChatStream(body: string | null): ChatMessage {
  if (body === null || body.length > 4_000_000) {
    throw new Error('Omi chat stream is malformed');
  }
  const parser = new IncrementalOmiChatParser();
  const events = [...parser.push(body), ...parser.finish()];
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.kind === 'done') {
      return event.message;
    }
  }
  throw new Error('Omi chat ended without a terminal message');
}
