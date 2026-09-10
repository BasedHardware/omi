import type {OmiBackend} from './omiNativeTypes';
import {visibleDisplayText} from './desktopReadClient';

const MAX_VOCABULARY = 1000;

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

function vocabulary(value: unknown): string[] {
  if (!Array.isArray(value) || value.length > MAX_VOCABULARY) {
    throw new TranscriptionPreferencesError();
  }
  const words: string[] = [];
  for (const raw of value) {
    if (typeof raw !== 'string') {
      throw new TranscriptionPreferencesError();
    }
    const word = visibleDisplayText(raw);
    if (word !== '') {
      words.push(word);
    }
  }
  return words;
}

export type OmiTranscriptionPreferences = {
  singleLanguageMode: boolean | undefined;
  vocabulary: string[];
};

export function parseOmiTranscriptionPreferences(
  body: string,
): OmiTranscriptionPreferences {
  const record = object(JSON.parse(body));
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
        : undefined,
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
