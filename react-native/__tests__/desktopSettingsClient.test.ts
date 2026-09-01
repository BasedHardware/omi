import {
  defaultDesktopPreferences,
  parseAudioRecordingMode,
  parseStampedV5Origin,
} from '../src/desktopSettingsClient';
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
