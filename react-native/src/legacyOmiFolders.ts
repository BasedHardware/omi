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
function array(value: unknown): unknown[] {
  if (!Array.isArray(value)) {
    throw new FoldersError();
  }
  return value;
}

const FOLDER_HEX_COLOR = /^#?[0-9A-Fa-f]{6}$/;

export function folderDefaultColorCopy(): string {
  return '#6B7280';
}

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

export function omiFolderColorCopy(value: unknown): string | undefined {
  if (value === undefined) {
    return folderDefaultColorCopy();
  }
  if (typeof value !== 'string') {
    return undefined;
  }
  return omiFolderHexColor(value) ?? folderDefaultColorCopy();
}

export function omiFolderFill(color: string, alpha: number): string {
  const hex = color.startsWith('#') ? color.slice(1) : color;
  return `rgba(${Number.parseInt(hex.slice(0, 2), 16)}, ${Number.parseInt(
    hex.slice(2, 4),
    16,
  )}, ${Number.parseInt(hex.slice(4, 6), 16)}, ${alpha})`;
}

export function parseOmiFolders(body: string): OmiFolder[] {
  const rows = array(JSON.parse(body));
  const folders: OmiFolder[] = [];
  const names = new Map<string, string>();
  for (const raw of rows) {
    const folder = object(raw);
    const id = text(folder.id, 1_000_000);
    if (names.has(id)) {
      throw new FoldersError();
    }
    if (typeof folder.name !== 'string') {
      continue;
    }
    const name = text(folder.name, 1_000_000);
    names.set(id, name);
    const color = omiFolderColorCopy(folder.color);
    const icon =
      folder.icon === undefined
        ? undefined
        : visibleDisplayText(text(folder.icon, 1_000_000));
    folders.push({
      id,
      name,
      ...(color === undefined ? {} : {color}),
      ...(icon === undefined || icon === '' || icon === 'folder'
        ? {}
        : {icon}),
    });
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
  icon?: string;
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
