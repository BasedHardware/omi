import {
  defaultDesktopPreferences,
  loadDesktopPreferences,
  parseAudioRecordingMode,
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
  expect(parseSoftwarePlane('new')).toBe('new');
  expect(parseAudioRecordingMode('meetings')).toBe('meetings');
  expect(parseAudioRecordingMode('off')).toBe('off');
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
