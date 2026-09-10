import type {ChatMessage} from './chatClient';
import {visibleDisplayText} from './desktopReadClient';
import type {OmiBackend} from './omiNativeTypes';

const MAX_CHAT_APP_LOOKUPS = 20;

class AppError extends Error {
  constructor() {
    super('Omi app is malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new AppError();
  }
  return value as Record<string, unknown>;
}

export function parseOmiAppName(body: string, appId: string): string {
  const row = object(JSON.parse(body));
  if (row.deleted === true) {
    throw new AppError();
  }
  const id = visibleDisplayText(typeof row.id === 'string' ? row.id : '');
  const name = visibleDisplayText(typeof row.name === 'string' ? row.name : '');
  if (id !== appId || name === '') {
    throw new AppError();
  }
  return name;
}

export async function loadOmiAppNames(
  backend: OmiBackend,
  appIds: readonly string[],
): Promise<Map<string, string>> {
  const unique: string[] = [];
  const seen = new Set<string>();
  for (const raw of appIds) {
    const id = visibleDisplayText(raw);
    if (id === '' || seen.has(id)) {
      continue;
    }
    seen.add(id);
    unique.push(id);
    if (unique.length === MAX_CHAT_APP_LOOKUPS) {
      break;
    }
  }
  const names = new Map<string, string>();
  await Promise.all(
    unique.map(async id => {
      const name = await loadOmiAppName(backend, id);
      if (name !== null) {
        names.set(id, name);
      }
    }),
  );
  return names;
}

async function loadOmiAppName(
  backend: OmiBackend,
  appId: string,
): Promise<string | null> {
  const response = await backend.request({
    id: 'omi-app',
    method: 'GET',
    expectedApiContract: 'omi',
    path: `/v1/apps/${encodeURIComponent(appId)}`,
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return null;
  }
  try {
    return parseOmiAppName(response.body, appId);
  } catch {
    return null;
  }
}

export async function attachOmiChatAppNames(
  backend: OmiBackend,
  messages: ChatMessage[],
): Promise<ChatMessage[]> {
  const ids = messages.flatMap(message =>
    message.appId === undefined ? [] : [message.appId],
  );
  if (ids.length === 0) {
    return messages;
  }
  const names = await loadOmiAppNames(backend, ids);
  return messages.map(message => {
    if (message.appId === undefined) {
      return message;
    }
    const name = names.get(message.appId);
    if (name === undefined) {
      return message;
    }
    return {...message, appName: name};
  });
}
