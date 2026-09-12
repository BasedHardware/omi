import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

const TASK_INTEGRATION_NAMES: Record<string, string> = {
  apple_reminders: 'Apple Reminders',
  asana: 'Asana',
  clickup: 'ClickUp',
  google_tasks: 'Google Tasks',
  monday: 'Monday',
  todoist: 'Todoist',
  trello: 'Trello',
};

class TaskIntegrationError extends Error {
  constructor() {
    super('Omi task integrations are malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new TaskIntegrationError();
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, limit: number): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new TaskIntegrationError();
  }
  return value;
}

export type OmiTaskIntegration = {
  key: string;
  name: string;
  isDefault: boolean;
};

export function taskIntegrationName(key: string): string {
  return TASK_INTEGRATION_NAMES[key] ?? key;
}

export function taskIntegrationRowCopy(row: OmiTaskIntegration): string {
  return row.isDefault ? `${row.name} · Default` : row.name;
}

export function parseOmiTaskIntegrations(body: string): OmiTaskIntegration[] {
  const record = object(JSON.parse(body));
  const integrations = object(record.integrations);
  const keys = Object.keys(integrations);
  const defaultApp =
    record.default_app === undefined || record.default_app === null
      ? ''
      : visibleDisplayText(text(record.default_app, 10000));
  const items: OmiTaskIntegration[] = [];
  for (const rawKey of keys) {
    const key = visibleDisplayText(text(rawKey, 10000));
    if (key === '') {
      continue;
    }
    const rawDetails = integrations[rawKey];
    if (
      rawDetails === null ||
      typeof rawDetails !== 'object' ||
      Array.isArray(rawDetails)
    ) {
      continue;
    }
    const details = rawDetails as Record<string, unknown>;
    if (details.connected !== true) {
      continue;
    }
    items.push({
      key,
      name: taskIntegrationName(key),
      isDefault: defaultApp !== '' && defaultApp === key,
    });
  }
  return items;
}

export async function loadOmiTaskIntegrations(
  backend: OmiBackend,
): Promise<OmiTaskIntegration[]> {
  const response = await backend.request({
    id: 'omi-task-integrations',
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/task-integrations',
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return [];
  }
  try {
    return parseOmiTaskIntegrations(response.body);
  } catch {
    return [];
  }
}
