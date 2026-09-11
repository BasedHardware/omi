import {
  defaultDesktopPreferences,
  loadDesktopPreferences,
  parseAudioRecordingMode,
  parseLiveVoiceProvider,
  parseStampedV5Origin,
  setDesktopPreference,
} from '../src/desktopSettingsClient';
import {NativeModules} from 'react-native';
import {
  parseSoftwarePlane,
  SOFTWARE_PLANE_DEFAULTS_KEY,
} from '../src/v5BackendOrigin';

test('desktop settings persist the Advanced software plane locally', () => {
  expect(SOFTWARE_PLANE_DEFAULTS_KEY).toBe('omi.backend.softwarePlane');
  expect(defaultDesktopPreferences().softwarePlane).toBe('old');
  expect(defaultDesktopPreferences().liveVoiceProvider).toBe('gpt_live');
  expect(parseSoftwarePlane('new')).toBe('new');
  expect(parseAudioRecordingMode('meetings')).toBe('meetings');
  expect(parseAudioRecordingMode('off')).toBe('off');
  expect(parseLiveVoiceProvider('gemini_live')).toBe('gemini_live');
  expect(parseLiveVoiceProvider('gpt_live')).toBe('gpt_live');
  expect(parseLiveVoiceProvider(undefined)).toBe('gpt_live');
  expect(parseLiveVoiceProvider('nope')).toBe('gpt_live');
  expect(
    parseStampedV5Origin('https://omi-v5-backend-staging.example.workers.dev'),
  ).toBe('https://omi-v5-backend-staging.example.workers.dev');
  expect(parseStampedV5Origin('https://evil.example')).toBeNull();
  expect(parseStampedV5Origin(undefined)).toBeNull();
});

test('loads and writes the backend plane through desktop preferences', async () => {
  const modules = NativeModules as {
    OmiDesktopCommands?: {
      loadDesktopPreferences(): Promise<Record<string, unknown>>;
      setDesktopPreference(
        key: string,
        value: string,
      ): Promise<Record<string, unknown>>;
    };
  };
  const setDesktopPreferenceNative = jest.fn(async () => ({
    softwarePlane: 'old',
    stampedV5Origin: 'https://omi-v5-backend-staging.example.workers.dev',
  }));
  modules.OmiDesktopCommands = {
    loadDesktopPreferences: async () => ({
      softwarePlane: null,
      stampedV5Origin: 'https://omi-v5-backend-staging.example.workers.dev',
    }),
    setDesktopPreference: setDesktopPreferenceNative,
  };

  await expect(loadDesktopPreferences()).resolves.toMatchObject({
    softwarePlane: 'new',
    stampedV5Origin: 'https://omi-v5-backend-staging.example.workers.dev',
  });
  await expect(
    setDesktopPreference('softwarePlane', 'old'),
  ).resolves.toMatchObject({softwarePlane: 'old'});
  expect(setDesktopPreferenceNative).toHaveBeenCalledWith(
    'softwarePlane',
    'old',
  );

  delete modules.OmiDesktopCommands;
});

test('loads and writes the live voice provider through desktop preferences', async () => {
  const modules = NativeModules as {
    OmiDesktopCommands?: {
      loadDesktopPreferences(): Promise<Record<string, unknown>>;
      setDesktopPreference(
        key: string,
        value: string,
      ): Promise<Record<string, unknown>>;
    };
  };
  const setDesktopPreferenceNative = jest.fn(async () => ({
    softwarePlane: 'old',
    liveVoiceProvider: 'gemini_live',
    stampedV5Origin: null,
  }));
  modules.OmiDesktopCommands = {
    loadDesktopPreferences: async () => ({
      softwarePlane: 'old',
      liveVoiceProvider: 'gpt_live',
      stampedV5Origin: null,
    }),
    setDesktopPreference: setDesktopPreferenceNative,
  };

  await expect(loadDesktopPreferences()).resolves.toMatchObject({
    liveVoiceProvider: 'gpt_live',
  });
  await expect(
    setDesktopPreference('liveVoiceProvider', 'gemini_live'),
  ).resolves.toMatchObject({liveVoiceProvider: 'gemini_live'});
  expect(setDesktopPreferenceNative).toHaveBeenCalledWith(
    'liveVoiceProvider',
    'gemini_live',
  );

  delete modules.OmiDesktopCommands;
});
