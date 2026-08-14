import {resolveOmiNative, type OmiNative} from '../src/omiNative';

test('native module selection keeps a registered implementation', () => {
  const nativeModule = {} as OmiNative;

  const selected = resolveOmiNative(nativeModule);

  expect(selected.installed).toBe(true);
  expect(selected.adapter).toBe(nativeModule);
});

test('native module selection reports an unavailable platform without a simulator', () => {
  const selected = resolveOmiNative(undefined);

  expect(selected.installed).toBe(false);
  expect(selected.adapter).toBeUndefined();
});
