import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

class TranscriptionPreferencesError extends Error {
  constructor() {
    super('Omi transcription preferences are malformed');
  }
}

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new TranscriptionPreferencesError();
  }
  return value as Record<string, unknown>;
}

function presentNullableDate(value: unknown): void {
  if (value === undefined || value === null) {
    return;
  }
  if (typeof value !== 'string') {
    throw new TranscriptionPreferencesError();
  }
  if (visibleDisplayText(value) !== value) {
    throw new TranscriptionPreferencesError();
  }
  const parsed = Date.parse(value.replace(/([+-]\d{2})$/, '$1:00'));
  if (value === '' || !Number.isFinite(parsed)) {
    throw new TranscriptionPreferencesError();
  }
}

function vocabulary(value: unknown): string[] {
  if (!Array.isArray(value)) {
    throw new TranscriptionPreferencesError();
  }
  const words: string[] = [];
  for (const raw of value) {
    if (typeof raw !== 'string') {
      throw new TranscriptionPreferencesError();
    }
    words.push(raw);
  }
  return words;
}

export type OmiTranscriptionPreferences = {
  singleLanguageMode: boolean;
  vocabulary: string[];
};

export function parseOmiTranscriptionPreferences(
  body: string,
): OmiTranscriptionPreferences {
  const record = object(JSON.parse(body));
  presentNullableDate(record.custom_stt_since);
  if (
    record.single_language_mode !== undefined &&
    typeof record.single_language_mode !== 'boolean'
  ) {
    throw new TranscriptionPreferencesError();
  }
  return {
    singleLanguageMode:
      typeof record.single_language_mode === 'boolean'
        ? record.single_language_mode
        : false,
    vocabulary:
      record.vocabulary === undefined || record.vocabulary === null
        ? []
        : vocabulary(record.vocabulary),
  };
}

export async function loadOmiTranscriptionPreferences(
  backend: OmiBackend,
): Promise<OmiTranscriptionPreferences | null> {
  const response = await backend.request({
    id: 'omi-transcription-preferences',
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/transcription-preferences',
  });
  if (
    response.status !== 200 ||
    response.body === null ||
    response.body.length > 1024 * 1024
  ) {
    return null;
  }
  try {
    return parseOmiTranscriptionPreferences(response.body);
  } catch {
    return null;
  }
}
