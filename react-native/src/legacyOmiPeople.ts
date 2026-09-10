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
function array(value: unknown, limit: number): unknown[] {
  if (!Array.isArray(value) || value.length > limit) {
    throw new PeopleError();
  }
  return value;
}

export function parseOmiPeopleNames(body: string): Map<string, string> {
  const rows = array(JSON.parse(body), 1000);
  const names = new Map<string, string>();
  for (const raw of rows) {
    const person = object(raw);
    const id = visibleDisplayText(text(person.id, 256));
    if (id === '') {
      throw new PeopleError();
    }
    if (names.has(id)) {
      throw new PeopleError();
    }
    const name = visibleDisplayText(text(person.name, 10000));
    if (name !== '') {
      names.set(id, name);
    }
  }
  return names;
}

export async function loadOmiPeopleNames(
  backend: OmiBackend,
  signal?: AbortSignal,
): Promise<Map<string, string>> {
  if (signal?.aborted) {
    return new Map();
  }
  const response = await backend.request({
    id: 'omi-people',
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/people?include_speech_samples=false',
  });
  if (signal?.aborted) {
    return new Map();
  }
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return new Map();
  }
  try {
    return parseOmiPeopleNames(response.body);
  } catch {
    return new Map();
  }
}
