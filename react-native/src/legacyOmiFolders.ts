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

const FOLDER_HEX_COLOR = /^#?[0-9A-Fa-f]{6}$/;

export function omiFolderHexColor(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }
  const color = value.trim();
  if (!FOLDER_HEX_COLOR.test(color)) {
    return undefined;
  }
  return (color.startsWith('#') ? color : `#${color}`).toUpperCase();
}

export function omiFolderFill(color: string, alpha: number): string {
  const hex = color.startsWith('#') ? color.slice(1) : color;
  return `rgba(${Number.parseInt(hex.slice(0, 2), 16)}, ${Number.parseInt(
    hex.slice(2, 4),
    16,
  )}, ${Number.parseInt(hex.slice(4, 6), 16)}, ${alpha})`;
}

export function parseOmiFolders(body: string): OmiFolder[] {
  const rows = array(JSON.parse(body), 1000);
  const folders: OmiFolder[] = [];
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
    if (typeof folder.name !== 'string') {
      continue;
    }
    const name = visibleDisplayText(text(folder.name, 10000));
    if (name === '') {
      continue;
    }
    names.set(id, name);
    const color = omiFolderHexColor(folder.color);
    folders.push(color === undefined ? {id, name} : {id, name, color});
  }
  return folders;
}

export function parseOmiFolderNames(body: string): Map<string, string> {
  return new Map(parseOmiFolders(body).map(folder => [folder.id, folder.name]));
}

export type OmiFolder = {
  id: string;
  name: string;
  color?: string;
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
    return parseOmiFolders(response.body);
  } catch {
    return [];
  }
}

export async function loadOmiFolder(
  backend: OmiBackend,
  folderId: string,
  signal?: AbortSignal,
): Promise<OmiFolder | undefined> {
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
  try {
    return parseOmiFolders(response.body).find(
      folder => folder.id === folderId,
    );
  } catch {
    return undefined;
  }
}

export async function loadOmiFolderName(
  backend: OmiBackend,
  folderId: string,
  signal?: AbortSignal,
): Promise<string | undefined> {
  return (await loadOmiFolder(backend, folderId, signal))?.name;
}
