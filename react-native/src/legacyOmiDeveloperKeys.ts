import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

class DeveloperKeyError extends Error {
  constructor() {
    super('Omi developer keys are malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new DeveloperKeyError();
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, limit: number): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new DeveloperKeyError();
  }
  return value;
}

function array(value: unknown, limit: number): unknown[] {
  if (!Array.isArray(value) || value.length > limit) {
    throw new DeveloperKeyError();
  }
  return value;
}

export type OmiDeveloperKey = {
  id: string;
  name: string;
  keyPrefix: string;
  createdAtMs?: number;
  scopes?: string[];
};

function createdAtMs(value: unknown): number | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  const raw = visibleDisplayText(text(value, 10000));
  if (raw === '') {
    return undefined;
  }
  const parsed = Date.parse(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return undefined;
  }
  return parsed;
}

function optionalScopes(value: unknown): string[] | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  if (!Array.isArray(value)) {
    throw new DeveloperKeyError();
  }
  const scopes: string[] = [];
  for (const raw of value) {
    const scope = visibleDisplayText(text(raw, 10000));
    if (scope === '') {
      continue;
    }
    scopes.push(scope);
  }
  return scopes.length === 0 ? undefined : scopes;
}

export function parseOmiDeveloperKeys(body: string): OmiDeveloperKey[] {
  const rows = array(JSON.parse(body), 1000);
  const keys: OmiDeveloperKey[] = [];
  const seen = new Set<string>();
  for (const raw of rows) {
    const row = object(raw);
    const id = visibleDisplayText(text(row.id, 10000));
    if (id === '') {
      throw new DeveloperKeyError();
    }
    if (seen.has(id)) {
      throw new DeveloperKeyError();
    }
    seen.add(id);
    const name = visibleDisplayText(text(row.name, 1_000_000));
    if (name === '') {
      continue;
    }
    const keyPrefix = visibleDisplayText(text(row.key_prefix, 10000));
    const created = createdAtMs(row.created_at);
    const scopes = optionalScopes(row.scopes);
    keys.push({
      id,
      name,
      keyPrefix,
      ...(created === undefined ? {} : {createdAtMs: created}),
      ...(scopes === undefined ? {} : {scopes}),
    });
  }
  return keys;
}

async function loadKeys(
  backend: OmiBackend,
  id: string,
  path: string,
): Promise<OmiDeveloperKey[]> {
  const response = await backend.request({
    id,
    method: 'GET',
    expectedApiContract: 'omi',
    path,
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return [];
  }
  try {
    return parseOmiDeveloperKeys(response.body);
  } catch {
    return [];
  }
}

export async function loadOmiDevApiKeys(
  backend: OmiBackend,
): Promise<OmiDeveloperKey[]> {
  return loadKeys(backend, 'omi-dev-keys', '/v1/dev/keys');
}

export async function loadOmiMcpApiKeys(
  backend: OmiBackend,
): Promise<OmiDeveloperKey[]> {
  return loadKeys(backend, 'omi-mcp-keys', '/v1/mcp/keys');
}
