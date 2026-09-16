import type {ChatMessage} from './chatClient';
import {appImageUrl, visibleDisplayText} from './desktopReadClient';
import type {OmiBackend} from './omiNativeTypes';

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

function presentPaddedKnown(value: unknown): void {
  if (typeof value === 'string' && visibleDisplayText(value) !== value) {
    throw new AppError();
  }
}

function presentReview(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value !== 'object' || Array.isArray(value)) {
    return;
  }
  const review = value as Record<string, unknown>;
  presentPaddedKnown(review.rated_at);
  presentPaddedKnown(review.responded_at);
  presentPaddedKnown(review.score);
}

function presentReviews(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (!Array.isArray(value)) {
    return;
  }
  for (const raw of value) {
    presentReview(raw);
  }
}

export type OmiAppChrome = {
  name: string;
  description?: string;
  image?: string;
};

export function parseOmiApp(body: string, appId: string): OmiAppChrome {
  const row = object(JSON.parse(body));
  if (row.deleted === true) {
    throw new AppError();
  }
  const id = typeof row.id === 'string' ? row.id : '';
  if (typeof row.name !== 'string') {
    throw new AppError();
  }
  const name = row.name;
  if (id !== appId) {
    throw new AppError();
  }
  presentPaddedKnown(row.created_at);
  presentPaddedKnown(row.installs);
  presentPaddedKnown(row.rating_avg);
  presentPaddedKnown(row.rating_count);
  presentPaddedKnown(row.price);
  presentPaddedKnown(row.score);
  presentPaddedKnown(row.money_made);
  presentPaddedKnown(row.usage_count);
  presentReviews(row.reviews);
  presentReview(row.user_review);
  const image = appImageUrl(typeof row.image === 'string' ? row.image : '');
  if (row.description === undefined || row.description === null) {
    return image === null ? {name} : {name, image};
  }
  if (typeof row.description !== 'string') {
    throw new AppError();
  }
  const description = row.description;
  return {
    name,
    description,
    ...(image === null ? {} : {image}),
  };
}

export async function loadOmiApps(
  backend: OmiBackend,
  appIds: readonly string[],
): Promise<Map<string, OmiAppChrome>> {
  const unique: string[] = [];
  const seen = new Set<string>();
  for (const raw of appIds) {
    const id = visibleDisplayText(raw);
    if (id === '' || seen.has(id)) {
      continue;
    }
    seen.add(id);
    unique.push(id);
  }
  const apps = new Map<string, OmiAppChrome>();
  await Promise.all(
    unique.map(async id => {
      const app = await loadOmiApp(backend, id);
      if (app !== null) {
        apps.set(id, app);
      }
    }),
  );
  return apps;
}

async function loadOmiApp(
  backend: OmiBackend,
  appId: string,
): Promise<OmiAppChrome | null> {
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
    return parseOmiApp(response.body, appId);
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
  const apps = await loadOmiApps(backend, ids);
  return messages.map(message => {
    if (message.appId === undefined) {
      return message;
    }
    const app = apps.get(message.appId);
    if (app === undefined) {
      return message;
    }
    return {
      ...message,
      appName: app.name,
      ...(app.image === undefined ? {} : {appImage: app.image}),
    };
  });
}
