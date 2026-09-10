import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

export const OMI_INTEGRATION_KEYS = [
  'apple_health',
  'google_calendar',
  'gmail',
] as const;

export type OmiIntegrationKey = (typeof OMI_INTEGRATION_KEYS)[number];

const INTEGRATION_NAMES: Record<OmiIntegrationKey, string> = {
  apple_health: 'Apple Health',
  google_calendar: 'Google Calendar',
  gmail: 'Gmail',
};

class IntegrationError extends Error {
  constructor() {
    super('Omi integrations are malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new IntegrationError();
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, limit: number): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new IntegrationError();
  }
  return value;
}

export type OmiIntegration = {
  key: OmiIntegrationKey;
  name: string;
};

export function integrationName(key: OmiIntegrationKey): string {
  return INTEGRATION_NAMES[key];
}

export function parseOmiIntegration(
  body: string,
  key: OmiIntegrationKey,
): OmiIntegration | null {
  const row = object(JSON.parse(body));
  if (typeof row.connected !== 'boolean') {
    throw new IntegrationError();
  }
  const appKey = visibleDisplayText(text(row.app_key, 256));
  if (appKey !== key) {
    throw new IntegrationError();
  }
  if (row.connected !== true) {
    return null;
  }
  return {key, name: integrationName(key)};
}

async function loadOmiIntegration(
  backend: OmiBackend,
  key: OmiIntegrationKey,
): Promise<OmiIntegration | null> {
  const response = await backend.request({
    id: 'omi-integrations',
    method: 'GET',
    expectedApiContract: 'omi',
    path: `/v1/integrations/${encodeURIComponent(key)}`,
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return null;
  }
  try {
    return parseOmiIntegration(response.body, key);
  } catch {
    return null;
  }
}

export async function loadOmiIntegrations(
  backend: OmiBackend,
): Promise<OmiIntegration[]> {
  const rows = await Promise.all(
    OMI_INTEGRATION_KEYS.map(key => loadOmiIntegration(backend, key)),
  );
  return rows.flatMap(row => (row === null ? [] : [row]));
}
