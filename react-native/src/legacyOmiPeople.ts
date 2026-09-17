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

function presentPaddedKnown(value: unknown): void {
  if (typeof value === 'string' && visibleDisplayText(value) !== value) {
    throw new PeopleError();
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
    presentPaddedKnown(person.created_at);
    presentPaddedKnown(person.updated_at);
    presentPaddedKnown(person.speech_samples_version);
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
