import {
  firmwareLatestQuery,
  loadOmiLatestFirmware,
  parseOmiLatestFirmware,
} from './legacyOmiFirmware';
import type {OmiBackend} from './omiNativeTypes';

test('firmware latest query omits until model firmware hardware and manufacturer are visible', () => {
  expect(firmwareLatestQuery({model: 'Omi', firmware: '1.2.3'})).toBeNull();
  expect(
    firmwareLatestQuery({
      model: 'Omi Dev Kit',
      firmware: '1.2.3',
      hardware: '1',
      manufacturer: 'Based Hardware',
    }),
  ).toEqual({
    model: 'Omi Dev Kit',
    firmware: '1.2.3',
    hardware: '1',
    manufacturer: 'Based Hardware',
  });
});

test('parses GET latest firmware and omits empty or draft versions', () => {
  expect(parseOmiLatestFirmware(JSON.stringify({version: '1.3.0'}))).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
  });
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({version: '1.3.0', draft: true, min_version: '1.0.0'}),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: true,
    minVersion: '1.0.0',
  });
  expect(parseOmiLatestFirmware(JSON.stringify({version: ' \t'}))).toBeNull();
  expect(parseOmiLatestFirmware(JSON.stringify({}))).toBeNull();
});

test('fails closed for malformed GET latest firmware', () => {
  expect(() => parseOmiLatestFirmware(JSON.stringify([]))).toThrow();
  expect(() => parseOmiLatestFirmware(JSON.stringify({version: 1}))).toThrow();
  expect(() =>
    parseOmiLatestFirmware(JSON.stringify({version: '1.3.0', draft: 'yes'})),
  ).toThrow();
});

test('loadOmiLatestFirmware names resolved GET version and omits failures', async () => {
  const request = jest.fn(async () => ({
    id: 'firmware',
    status: 200,
    body: JSON.stringify({version: '1.3.0'}),
  }));
  const backend = {request} as unknown as OmiBackend;
  expect(
    await loadOmiLatestFirmware(backend, {
      model: 'Omi Dev Kit',
      firmware: '1.2.3',
      hardware: '1',
      manufacturer: 'Based Hardware',
    }),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
  });
  expect(request).toHaveBeenCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path: '/v2/firmware/latest?device_model=Omi%20Dev%20Kit&firmware_revision=1.2.3&hardware_revision=1&manufacturer_name=Based%20Hardware',
  });
  request.mockResolvedValueOnce({id: 'firmware', status: 500, body: '{}'});
  expect(
    await loadOmiLatestFirmware(backend, {
      model: 'Omi Dev Kit',
      firmware: '1.2.3',
      hardware: '1',
      manufacturer: 'Based Hardware',
    }),
  ).toBeNull();
});
