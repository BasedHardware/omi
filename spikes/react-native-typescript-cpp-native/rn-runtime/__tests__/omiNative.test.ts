import {omiNative, resolveOmiNative, type OmiNative} from '../src/omiNative';

test('native module selection prefers the registered implementation', () => {
  const nativeModule = {} as OmiNative;

  const selected = resolveOmiNative(nativeModule);

  expect(selected.installed).toBe(true);
  expect(selected.adapter).toBe(nativeModule);
});

test('native module selection falls back when no implementation is registered', () => {
  const selected = resolveOmiNative(undefined);

  expect(selected.installed).toBe(false);
  expect(selected.adapter).not.toBeUndefined();
  expect(selected.adapter).not.toBe(null);
});

test('host adapter exposes every Omi native capability category', async () => {
  const snapshot = await omiNative.getSnapshot();
  expect(snapshot.bluetooth).toBe('poweredOn');
  expect(await omiNative.startScan()).toHaveLength(2);
  await omiNative.connectDevice('mvp-omi-001');
  expect(await omiNative.readCharacteristic('mvp-omi-001', 'service', 'characteristic')).toEqual([0xaa, 0x55, 0x01, 0x00]);
  await omiNative.writeCharacteristic('mvp-omi-001', 'service', 'characteristic', [1, 2]);
  await omiNative.subscribeCharacteristic('mvp-omi-001', 'service', 'characteristic');
  await omiNative.startRssiStreaming('mvp-omi-001');
  expect((await omiNative.getDeviceDiagnostics('mvp-omi-001')).source).toBe('host-simulator');
  expect(await omiNative.getBatteryHistory('mvp-omi-001')).toHaveLength(1);
  await omiNative.startCapture('stream');
  await omiNative.stopCapture();
  expect(await omiNative.getAudioRoute()).toBe('phone-mic');
  await omiNative.startPhoneCall('+15550000000');
  await omiNative.setPhoneCallAudio(false, true);
  await omiNative.endPhoneCall();
  await omiNative.setNotificationOnKillService('Omi', 'Capturing');
  expect((await omiNative.getWifiNetwork()).connected).toBe(true);
  await omiNative.setBackgroundMode(true);
  expect((await omiNative.getWatchStatus()).paired).toBe(false);
  expect((await omiNative.getCameraStatus()).available).toBe(false);
  expect((await omiNative.capturePhoto()).accepted).toBe(false);
  await omiNative.disconnectDevice('mvp-omi-001');
});
