import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

const MAX_APP_CHANGELOGS = 5;

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

function array(value: unknown): unknown[] {
  if (!Array.isArray(value)) {
    throw new AppChangelogError();
  }
  return value;
}

function createdAtMs(value: unknown): number {
  const raw = text(value, 1_000_000);
  const parsed = Date.parse(raw.replace(/([+-]\d{2})$/, '$1:00'));
  if (!Number.isFinite(parsed)) {
    throw new AppChangelogError();
  }
  return parsed;
}

const ANNOUNCEMENT_TRIGGERS = new Set([
  'immediate',
  'version_upgrade',
  'firmware_upgrade',
]);

function optionalNullableString(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  text(value, 1_000_000);
}

function optionalNullableStringList(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (!Array.isArray(value)) {
    throw new AppChangelogError();
  }
  for (const item of value) {
    text(item, 1_000_000);
  }
}

function optionalBool(value: unknown): void {
  if (value === undefined) {
    return;
  }
  if (typeof value !== 'boolean') {
    throw new AppChangelogError();
  }
}

function optionalInt(value: unknown): void {
  if (value === undefined) {
    return;
  }
  if (typeof value === 'number' && Number.isInteger(value)) {
    return;
  }
  if (typeof value === 'string' && /^-?\d+$/.test(value)) {
    return;
  }
  throw new AppChangelogError();
}

function optionalDateTime(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  createdAtMs(value);
}

function optionalTargeting(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  const targeting = object(value);
  optionalNullableString(targeting.app_version_max);
  optionalNullableString(targeting.app_version_min);
  optionalNullableStringList(targeting.device_models);
  optionalNullableString(targeting.firmware_version_max);
  optionalNullableString(targeting.firmware_version_min);
  optionalNullableStringList(targeting.platforms);
  optionalNullableStringList(targeting.test_uids);
  if (targeting.trigger === undefined) {
    return;
  }
  const trigger = text(targeting.trigger, 1_000_000);
  if (!ANNOUNCEMENT_TRIGGERS.has(trigger)) {
    throw new AppChangelogError();
  }
}

function optionalDisplay(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  const display = object(value);
  optionalBool(display.dismissible);
  optionalDateTime(display.expires_at);
  optionalInt(display.priority);
  optionalBool(display.show_once);
  optionalDateTime(display.start_at);
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

export function appChangelogLoadedHeading(version: string): string {
  return `What's New in ${visibleDisplayText(version)}`;
}

export function appChangelogsLoadErrorCopy(): string {
  return 'Failed to load changelogs';
}

export function appChangelogRowCopy(
  title: string,
  description: string,
  icon = '',
): string {
  const prefix = visibleDisplayText(icon);
  const body = title === '' ? description : `${title} · ${description}`;
  return body === '' ? prefix : `${prefix} · ${body}`;
}

export function parseOmiAppChangelogs(body: string): OmiAppChangelogRow[] {
  const rows = array(JSON.parse(body));
  const items: OmiAppChangelogRow[] = [];
  const seen = new Set<string>();
  let named = 0;
  for (const raw of rows) {
    if (named === MAX_APP_CHANGELOGS) {
      break;
    }
    const row = object(raw);
    const type = text(row.type, 1_000_000);
    createdAtMs(row.created_at);
    text(row.id, 1_000_000);
    object(row.content);
    optionalTargeting(row.targeting);
    optionalDisplay(row.display);
    optionalBool(row.active);
    optionalNullableString(row.app_version);
    optionalNullableString(row.firmware_version);
    optionalNullableStringList(row.device_models);
    optionalDateTime(row.expires_at);
    if (type === 'feature' || type === 'announcement') {
      continue;
    }
    if (type !== 'changelog') {
      throw new AppChangelogError();
    }
    const id = text(row.id, 1_000_000);
    if (seen.has(id)) {
      throw new AppChangelogError();
    }
    seen.add(id);
    const version =
      row.app_version === undefined || row.app_version === null
        ? ''
        : visibleDisplayText(text(row.app_version, 1_000_000));
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
    const heading = appChangelogLoadedHeading(version);
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
      const title = visibleDisplayText(text(change.title, 1_000_000));
      const description =
        change.description === undefined || change.description === null
          ? ''
          : visibleDisplayText(text(change.description, 1_000_000));
      const icon =
        change.icon === undefined || change.icon === null
          ? '✨'
          : visibleDisplayText(text(change.icon, 1_000_000));
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
  return parseOmiAppChangelogs(response.body);
}
