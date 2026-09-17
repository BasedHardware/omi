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

function presentNullableDate(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value !== 'string') {
    throw new FoldersError();
  }
  if (visibleDisplayText(value) !== value) {
    throw new FoldersError();
  }
  const parsed = Date.parse(value.replace(/([+-]\d{2})$/, '$1:00'));
  if (value === '' || !Number.isFinite(parsed)) {
    throw new FoldersError();
  }
}

function presentDefaultInt(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value === 'string') {
    if (visibleDisplayText(value) !== value) {
      throw new FoldersError();
    }
    if (!/^[+-]?[0-9]+$/.test(value)) {
      throw new FoldersError();
    }
    return;
  }
  if (typeof value === 'number' && Number.isSafeInteger(value)) {
    return;
  }
  throw new FoldersError();
}

const FOLDER_HEX_COLOR = /^#?[0-9A-Fa-f]{6}$/;

const FOLDER_CUSTOM_ICONS: ReadonlySet<string> = new Set([
  '📁',
  '💼',
  '🏠',
  '📚',
  '👨‍👩‍👧‍👦',
  '👤',
  '👥',
  '❤️',
  '🎮',
  '✈️',
  '🏥',
  '🛒',
  '💰',
  '🎵',
  '🎨',
  '📝',
  '💬',
  '🌎',
  '🛠️',
  '🍔',
  '🏆',
  '🔒',
  '⭐',
  '🕐',
  '📊',
]);

export function folderDefaultColorCopy(): string {
  return '#6B7280';
}

export function omiFolderHexColor(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }
  if (!FOLDER_HEX_COLOR.test(value)) {
    return undefined;
  }
  return (value.startsWith('#') ? value : `#${value}`).toUpperCase();
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

export function omiFolderIconCopy(value: unknown): string | undefined {
  if (value === undefined) {
    return undefined;
  }
  const icon = text(value, 1_000_000);
  return FOLDER_CUSTOM_ICONS.has(icon) ? icon : undefined;
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
    const icon = omiFolderIconCopy(folder.icon);
    presentNullableDate(folder.created_at);
    presentNullableDate(folder.updated_at);
    presentDefaultInt(folder.conversation_count);
    presentDefaultInt(folder.order);
    folders.push({
      id,
      name,
      ...(color === undefined ? {} : {color}),
      ...(icon === undefined ? {} : {icon}),
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
  return parseOmiFolders(response.body);
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
  return parseOmiFolders(response.body).find(folder => folder.id === folderId);
}

export async function loadOmiFolderName(
  backend: OmiBackend,
  folderId: string,
  signal?: AbortSignal,
): Promise<string | undefined> {
  return (await loadOmiFolder(backend, folderId, signal))?.name;
}
