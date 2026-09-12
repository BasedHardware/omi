import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

const MAX_APP_CHANGELOGS = 5;
const MAX_APP_CHANGELOG_PARSE = 10;

class AppChangelogError extends Error {
  constructor() {
    super('Omi app changelogs are malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new AppChangelogError();
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, limit: number): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new AppChangelogError();
  }
  return value;
}

function array(value: unknown, limit: number): unknown[] {
  if (!Array.isArray(value) || value.length > limit) {
    throw new AppChangelogError();
  }
  return value;
}

export type OmiAppChangelogRow = {
  key: string;
  title: string;
  copy: string;
};

export function appChangelogHeading(version: string): string {
  const copy = visibleDisplayText(version);
  return copy === '' ? "What's New" : `What's New in ${copy}`;
}

export function appChangelogRowCopy(
  title: string,
  description: string,
  icon = '',
): string {
  const prefix = visibleDisplayText(icon);
  const body = description === '' ? title : `${title} · ${description}`;
  return prefix === '' ? body : `${prefix} · ${body}`;
}

export function parseOmiAppChangelogs(body: string): OmiAppChangelogRow[] {
  const rows = array(JSON.parse(body), MAX_APP_CHANGELOG_PARSE);
  const items: OmiAppChangelogRow[] = [];
  const seen = new Set<string>();
  let named = 0;
  for (const raw of rows) {
    if (named === MAX_APP_CHANGELOGS) {
      break;
    }
    const row = object(raw);
    const type = visibleDisplayText(text(row.type, 64));
    if (type !== 'changelog') {
      continue;
    }
    const id = visibleDisplayText(text(row.id, 256));
    if (id === '') {
      throw new AppChangelogError();
    }
    if (seen.has(id)) {
      throw new AppChangelogError();
    }
    seen.add(id);
    const version =
      row.app_version === undefined || row.app_version === null
        ? ''
        : visibleDisplayText(text(row.app_version, 10000));
    const content = object(row.content);
    if (
      content.changes !== undefined &&
      content.changes !== null &&
      !Array.isArray(content.changes)
    ) {
      continue;
    }
    const changes =
      content.changes === undefined || content.changes === null
        ? []
        : (content.changes as unknown[]);
    const heading = appChangelogHeading(version);
    const pending: OmiAppChangelogRow[] = [];
    let changeIndex = 0;
    let projectable = true;
    for (const rawChange of changes) {
      if (
        rawChange === null ||
        typeof rawChange !== 'object' ||
        Array.isArray(rawChange)
      ) {
        projectable = false;
        break;
      }
      const change = rawChange as Record<string, unknown>;
      if (typeof change.title !== 'string') {
        projectable = false;
        break;
      }
      if (
        change.description !== undefined &&
        change.description !== null &&
        typeof change.description !== 'string'
      ) {
        projectable = false;
        break;
      }
      if (
        change.icon !== undefined &&
        change.icon !== null &&
        typeof change.icon !== 'string'
      ) {
        projectable = false;
        break;
      }
      const title = visibleDisplayText(text(change.title, 10000));
      if (title === '') {
        continue;
      }
      const description =
        change.description === undefined || change.description === null
          ? ''
          : visibleDisplayText(text(change.description, 10000));
      const icon =
        change.icon === undefined || change.icon === null
          ? ''
          : visibleDisplayText(text(change.icon, 10000));
      pending.push({
        key: `${id}:${changeIndex}`,
        title: heading,
        copy: appChangelogRowCopy(title, description, icon),
      });
      changeIndex += 1;
    }
    if (!projectable) {
      continue;
    }
    items.push(...pending);
    if (pending.length > 0) {
      named += 1;
    }
  }
  return items;
}

export async function loadOmiAppChangelogs(
  backend: OmiBackend,
): Promise<OmiAppChangelogRow[]> {
  const response = await backend.request({
    id: 'omi-app-changelogs',
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/announcements/changelogs?limit=5',
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return [];
  }
  try {
    return parseOmiAppChangelogs(response.body);
  } catch {
    return [];
  }
}
