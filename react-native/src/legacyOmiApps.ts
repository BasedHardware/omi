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

function presentNullableDate(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value !== 'string') {
    throw new AppError();
  }
  if (visibleDisplayText(value) !== value) {
    throw new AppError();
  }
  const parsed = Date.parse(value.replace(/([+-]\d{2})$/, '$1:00'));
  if (value === '' || !Number.isFinite(parsed)) {
    throw new AppError();
  }
}

function presentDefaultInt(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value === 'string') {
    if (visibleDisplayText(value) !== value) {
      throw new AppError();
    }
    if (!/^[+-]?[0-9]+$/.test(value)) {
      throw new AppError();
    }
    return;
  }
  if (typeof value === 'number' && Number.isSafeInteger(value)) {
    return;
  }
  throw new AppError();
}

function presentNullableDouble(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value === 'string') {
    if (visibleDisplayText(value) !== value) {
      throw new AppError();
    }
    if (value === '' || !Number.isFinite(Number(value))) {
      throw new AppError();
    }
    return;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return;
  }
  throw new AppError();
}

function presentNullableString(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value !== 'string') {
    throw new AppError();
  }
}

function presentReview(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  const review = object(value);
  presentNullableDate(review.rated_at);
  presentNullableDate(review.responded_at);
  presentNullableDouble(review.score);
  presentNullableString(review.review);
  presentNullableString(review.uid);
  presentNullableString(review.username);
  presentNullableString(review.response);
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

function presentObject(
  value: unknown,
  present: (row: Record<string, unknown>) => void,
): void {
  if (value === undefined || value === null) {
    return;
  }
  present(object(value));
}

function presentObjectList(
  value: unknown,
  present: (row: Record<string, unknown>) => void,
): void {
  if (value === undefined || value === null) {
    return;
  }
  if (!Array.isArray(value)) {
    return;
  }
  for (const raw of value) {
    presentObject(raw, present);
  }
}

function presentExternalIntegration(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  const row = object(value);
  presentNullableString(row.app_home_url);
  presentNullableString(row.chat_messages_target);
  presentNullableString(row.chat_tools_manifest_url);
  presentNullableString(row.mcp_server_url);
  presentNullableString(row.setup_completed_url);
  presentNullableString(row.setup_instructions_file_path);
  presentNullableString(row.triggers_on);
  presentNullableString(row.webhook_url);
  presentNullableMap(row.mcp_oauth_tokens);
  presentObjectList(row.actions, action => {
    presentNullableString(action.action);
  });
  presentObjectList(row.auth_steps, step => {
    presentNullableString(step.name);
    presentNullableString(step.url);
  });
}

function presentChatTools(value: unknown): void {
  presentObjectList(value, tool => {
    presentNullableString(tool.description);
    presentNullableString(tool.endpoint);
    presentNullableString(tool.method);
    presentNullableString(tool.name);
    presentNullableString(tool.status_message);
    presentNullableString(tool.transport);
    presentNullableMap(tool.parameters);
  });
}

function presentNullableMap(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  object(value);
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
  presentNullableDate(row.created_at);
  presentDefaultInt(row.installs);
  presentNullableDouble(row.rating_avg);
  presentDefaultInt(row.rating_count);
  presentNullableDouble(row.price);
  presentNullableDouble(row.score);
  presentNullableDouble(row.money_made);
  presentDefaultInt(row.usage_count);
  presentReviews(row.reviews);
  presentReview(row.user_review);
  presentNullableString(row.author);
  presentNullableString(row.category);
  presentNullableString(row.chat_prompt);
  presentNullableString(row.disabled_at);
  presentNullableString(row.disabled_error);
  presentNullableString(row.disabled_reason);
  presentNullableString(row.email);
  presentNullableString(row.memory_prompt);
  presentNullableString(row.payment_link);
  presentNullableString(row.payment_link_id);
  presentNullableString(row.payment_plan);
  presentNullableString(row.payment_price_id);
  presentNullableString(row.payment_product_id);
  presentNullableString(row.persona_prompt);
  presentNullableString(row.source_code_url);
  presentNullableString(row.status);
  presentNullableString(row.uid);
  presentNullableString(row.username);
  presentExternalIntegration(row.external_integration);
  presentChatTools(row.chat_tools);
  presentNullableMap(row.proactive_notification);
  presentNullableMap(row.twitter);
  presentNullableString(row.image);
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
