import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

const MAX_APP_CHANGELOGS = 5;
const MAX_APP_CHANGELOG_PARSE = 10;
const MAX_APP_CHANGELOG_CHANGES = 32;

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
        : visibleDisplayText(text(row.app_version, 64));
    const content = object(row.content);
    const changes =
      content.changes === undefined || content.changes === null
        ? []
        : array(content.changes, MAX_APP_CHANGELOG_CHANGES);
    const heading = appChangelogHeading(version);
    const before = items.length;
    let changeIndex = 0;
    for (const rawChange of changes) {
      const change = object(rawChange);
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
          : visibleDisplayText(text(change.icon, 32));
      items.push({
        key: `${id}:${changeIndex}`,
        title: heading,
        copy: appChangelogRowCopy(title, description, icon),
      });
      changeIndex += 1;
    }
    if (items.length > before) {
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
