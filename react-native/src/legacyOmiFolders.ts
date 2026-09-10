import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

class FoldersError extends Error {
  constructor() {
    super('Omi folders are malformed');
  }
}
function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new FoldersError();
  }
  return value as Record<string, unknown>;
}
function text(value: unknown, limit: number): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new FoldersError();
  }
  return value;
}
function array(value: unknown, limit: number): unknown[] {
  if (!Array.isArray(value) || value.length > limit) {
    throw new FoldersError();
  }
  return value;
}

export function parseOmiFolderNames(body: string): Map<string, string> {
  const rows = array(JSON.parse(body), 1000);
  const names = new Map<string, string>();
  for (const raw of rows) {
    const folder = object(raw);
    const id = visibleDisplayText(text(folder.id, 256));
    if (id === '') {
      throw new FoldersError();
    }
    if (names.has(id)) {
      throw new FoldersError();
    }
    const name = visibleDisplayText(text(folder.name, 10000));
    if (name !== '') {
      names.set(id, name);
    }
  }
  return names;
}

export type OmiFolder = {
  id: string;
  name: string;
};

export async function loadOmiFolderNames(
  backend: OmiBackend,
): Promise<OmiFolder[]> {
  const response = await backend.request({
    id: 'omi-folders',
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/folders',
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return [];
  }
  try {
    return [...parseOmiFolderNames(response.body)].map(([id, name]) => ({
      id,
      name,
    }));
  } catch {
    return [];
  }
}

export async function loadOmiFolderName(
  backend: OmiBackend,
  folderId: string,
  signal?: AbortSignal,
): Promise<string | undefined> {
  if (signal?.aborted) {
    return undefined;
  }
  const response = await backend.request({
    id: `omi-folders:${folderId}`,
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/folders',
  });
  if (signal?.aborted) {
    return undefined;
  }
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return undefined;
  }
  return parseOmiFolderNames(response.body).get(folderId);
}
