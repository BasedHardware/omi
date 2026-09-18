import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

class PeopleError extends Error {
  constructor() {
    super('Omi people are malformed');
  }
}
function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new PeopleError();
  }
  return value as Record<string, unknown>;
}
function text(value: unknown, limit: number): string {
  if (typeof value !== 'string' || value.length > limit) {
    throw new PeopleError();
  }
  return value;
}
function array(value: unknown): unknown[] {
  if (!Array.isArray(value)) {
    throw new PeopleError();
  }
  return value;
}

function presentNullableDate(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value !== 'string') {
    throw new PeopleError();
  }
  if (visibleDisplayText(value) !== value) {
    throw new PeopleError();
  }
  const parsed = Date.parse(value.replace(/([+-]\d{2})$/, '$1:00'));
  if (value === '' || !Number.isFinite(parsed)) {
    throw new PeopleError();
  }
}

function presentDefaultInt(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value === 'string') {
    if (visibleDisplayText(value) !== value) {
      throw new PeopleError();
    }
    if (!/^[+-]?[0-9]+$/.test(value)) {
      throw new PeopleError();
    }
    return;
  }
  if (typeof value === 'number' && Number.isSafeInteger(value)) {
    return;
  }
  throw new PeopleError();
}

function presentNullableInt(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value === 'number' && Number.isSafeInteger(value)) {
    return;
  }
  throw new PeopleError();
}

function presentUnusedStringListItems(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (!Array.isArray(value)) {
    return;
  }
  for (const item of value) {
    if (typeof item !== 'string') {
      throw new PeopleError();
    }
  }
}

export function parseOmiPeopleNames(body: string): Map<string, string> {
  const rows = array(JSON.parse(body));
  const names = new Map<string, string>();
  for (const raw of rows) {
    const person = object(raw);
    const id = text(person.id, 1_000_000);
    if (names.has(id)) {
      throw new PeopleError();
    }
    const name = text(person.name, 1_000_000);
    presentNullableDate(person.created_at);
    presentNullableDate(person.updated_at);
    presentDefaultInt(person.speech_samples_version);
    presentNullableInt(person.color_idx);
    presentUnusedStringListItems(person.speech_samples);
    presentUnusedStringListItems(person.speech_sample_transcripts);
    names.set(id, name);
  }
  return names;
}

export async function loadOmiPeopleNames(
  backend: OmiBackend,
  signal?: AbortSignal,
): Promise<Map<string, string> | null> {
  if (signal?.aborted) {
    return null;
  }
  const response = await backend.request({
    id: 'omi-people',
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/people?include_speech_samples=false',
  });
  if (signal?.aborted) {
    return null;
  }
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return null;
  }
  return parseOmiPeopleNames(response.body);
}
