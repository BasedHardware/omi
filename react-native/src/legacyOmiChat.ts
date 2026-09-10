import {decodeBase64} from './base64';
import type {
  ChatHistoryPage,
  ChatMessage,
  ChatMessageAttachment,
} from './chatClient';

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Omi chat message is malformed');
  }
  return value as Record<string, unknown>;
}

function parseOmiChatFiles(
  files: unknown,
  filesId: unknown,
): ChatMessageAttachment[] {
  if (files === undefined || files === null) {
    if (filesId === undefined || filesId === null) {
      return [];
    }
    if (
      !Array.isArray(filesId) ||
      filesId.length > 50 ||
      !filesId.every(id => typeof id === 'string')
    ) {
      throw new Error('Omi chat files are malformed');
    }
    return [];
  }
  if (!Array.isArray(files) || files.length > 50) {
    throw new Error('Omi chat files are malformed');
  }
  const ids =
    filesId === undefined || filesId === null
      ? []
      : Array.isArray(filesId) &&
        filesId.length <= 50 &&
        filesId.every(id => typeof id === 'string')
      ? filesId
      : null;
  if (ids === null) {
    throw new Error('Omi chat files are malformed');
  }
  if (files.length === 0 || ids.length === 0) {
    return [];
  }
  return files.map(raw => {
    const row = object(raw);
    const createdAt =
      typeof row.created_at === 'string' ? Date.parse(row.created_at) : NaN;
    if (
      typeof row.id !== 'string' ||
      row.id.length === 0 ||
      typeof row.name !== 'string' ||
      typeof row.mime_type !== 'string' ||
      typeof row.openai_file_id !== 'string' ||
      !Number.isFinite(createdAt)
    ) {
      throw new Error('Omi chat files are malformed');
    }
    return {
      id: row.id,
      displayName: row.name,
      mediaType: row.mime_type,
    };
  });
}

function parseOmiChatMemories(
  value: unknown,
): {title: string; emoji?: string}[] {
  if (value === undefined || value === null) {
    return [];
  }
  if (!Array.isArray(value) || value.length > 50) {
    throw new Error('Omi chat memories are malformed');
  }
  return value.map(raw => {
    const row = object(raw);
    const structured = object(row.structured);
    if (
      typeof structured.title !== 'string' ||
      typeof structured.emoji !== 'string'
    ) {
      throw new Error('Omi chat memories are malformed');
    }
    return {
      title: structured.title,
      ...(structured.emoji === '' ? {} : {emoji: structured.emoji}),
    };
  });
}

export function parseOmiMessage(value: unknown): ChatMessage {
  const row = object(value);
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
  const memories = parseOmiChatMemories(row.memories);
  const attachments = parseOmiChatFiles(row.files, row.files_id);
  return {
    id: row.id,
    text: row.text,
    sender: row.sender,
    ...(row.type === 'day_summary' ? {type: 'day_summary' as const} : {}),
    createdAt,
    generationOutcome: null,
    ...(memories.length === 0 ? {} : {memories}),
    ...(attachments.length === 0 ? {} : {attachments}),
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
  for (const frame of body.split(/\r?\n\r?\n/).reverse()) {
    if (!frame.startsWith('done: ')) continue;
    const bytes = decodeBase64(frame.slice(6).trim());
    const encoded = Array.from(
      bytes,
      byte => `%${byte.toString(16).padStart(2, '0')}`,
    ).join('');
    const message = parseOmiMessage(JSON.parse(decodeURIComponent(encoded)));
    if (message.sender !== 'ai')
      throw new Error('Omi chat terminal sender is invalid');
    return message;
  }
  throw new Error('Omi chat ended without a terminal message');
}
