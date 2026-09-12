/**
 * Regression tests for issue #13151:
 * Metro's JS-first resolution must not load stale JavaScript sources that
 * shadow the current TypeScript SDK entrypoints.
 *
 * package.json points `react-native`/`source` at extensionless `src/index`.
 * Legacy `src/index.js` beside `src/index.ts` causes Metro to load the retired
 * OmiModule bridge and throw during import.
 */

import fs from 'fs';
import path from 'path';

const SDK_ROOT = path.resolve(__dirname, '../..');
const SRC_DIR = path.join(SDK_ROOT, 'src');

/** Metro's default sourceExts order — `.js` is tried before `.ts`. */
const METRO_SOURCE_EXTS = ['js', 'jsx', 'json', 'ts', 'tsx'];

function metroWouldResolveToJs(relativeBase: string): string | null {
  for (const ext of METRO_SOURCE_EXTS) {
    const candidate = path.join(SRC_DIR, `${relativeBase}.${ext}`);
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

jest.mock('react-native', () => ({
  Platform: { OS: 'ios', select: (options: Record<string, string>) => options.ios ?? options.default },
}));

jest.mock('react-native-ble-plx', () => ({
  BleManager: jest.fn().mockImplementation(() => ({
    startDeviceScan: jest.fn(),
    stopDeviceScan: jest.fn(),
    state: jest.fn(() => Promise.resolve('PoweredOn')),
  })),
  Subscription: jest.fn(),
  Device: jest.fn(),
}));

describe('SDK entrypoint resolution (issue #13151)', () => {
  it('does not ship stale JavaScript sources that shadow TypeScript entrypoints', () => {
    expect(fs.existsSync(path.join(SRC_DIR, 'index.js'))).toBe(false);
    expect(fs.existsSync(path.join(SRC_DIR, 'types.js'))).toBe(false);
  });

  it('resolves src/index to the TypeScript implementation under Metro sourceExts', () => {
    const resolved = metroWouldResolveToJs('index');
    expect(resolved).not.toBeNull();
    expect(resolved).toMatch(/index\.ts$/);
  });

  it('resolves src/types to the TypeScript implementation under Metro sourceExts', () => {
    const resolved = metroWouldResolveToJs('types');
    expect(resolved).not.toBeNull();
    expect(resolved).toMatch(/types\.ts$/);
  });

  it('imports the current SDK entry without the retired OmiModule bridge', async () => {
    const sdk = await import('../index');

    expect(sdk.OmiConnection).toBeDefined();
    expect(sdk.VERSION).toBeDefined();
    expect(sdk.createTranscriber).toBeDefined();
    expect(sdk.mapCodecToName).toBeDefined();
    expect(sdk.DeviceConnectionState.CONNECTING).toBe('connecting');
    expect(sdk.DeviceConnectionState.DISCONNECTING).toBe('disconnecting');
    expect(sdk).not.toHaveProperty('OmiModule');
  });
});
