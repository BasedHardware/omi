import {
  loadOmiTranscriptionPreferences,
  parseOmiTranscriptionPreferences,
} from './legacyOmiTranscriptionPreferences';
import type {OmiBackend} from './omiNativeTypes';

test('parses GET transcription preferences without Flutter false defaults', () => {
  expect(
    parseOmiTranscriptionPreferences(
      JSON.stringify({
        vocabulary: ['Omi', ' \t', 'Based Hardware'],
        single_language_mode: true,
      }),
    ),
  ).toEqual({
    singleLanguageMode: true,
    vocabulary: ['Omi', 'Based Hardware'],
  });
  expect(parseOmiTranscriptionPreferences(JSON.stringify({}))).toEqual({
    singleLanguageMode: undefined,
    vocabulary: [],
  });
});

test('fails closed for malformed GET transcription preferences', () => {
  expect(() => parseOmiTranscriptionPreferences(JSON.stringify([]))).toThrow();
  expect(() =>
    parseOmiTranscriptionPreferences(JSON.stringify({vocabulary: ['Omi', 1]})),
  ).toThrow();
  expect(() =>
    parseOmiTranscriptionPreferences(
      JSON.stringify({single_language_mode: 'true'}),
    ),
  ).toThrow();
});

test('loadOmiTranscriptionPreferences names resolved GET preferences and omits failures', async () => {
  const request = jest.fn(async () => ({
    id: 'prefs',
    status: 200,
    body: JSON.stringify({
      vocabulary: ['Omi'],
      single_language_mode: false,
    }),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(await loadOmiTranscriptionPreferences(backend)).toEqual({
    singleLanguageMode: false,
    vocabulary: ['Omi'],
  });
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v1/users/transcription-preferences',
  });
  request.mockResolvedValueOnce({id: 'prefs', status: 404, body: '{}'});
  expect(await loadOmiTranscriptionPreferences(backend)).toBeNull();
  request.mockResolvedValueOnce({id: 'prefs', status: 200, body: '['});
  expect(await loadOmiTranscriptionPreferences(backend)).toBeNull();
});
