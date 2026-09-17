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

test('names Flutter FirmwareUpdate padded BLE firmwareLatestQuery instead of remapping to latest', () => {
  expect(
    firmwareLatestQuery({
      model: '  Omi Dev Kit  ',
      firmware: '  1.2.3  ',
      hardware: '1 ',
      manufacturer: '\u0085Based Hardware',
    }),
  ).toEqual({
    model: '  Omi Dev Kit  ',
    firmware: '  1.2.3  ',
    hardware: '1 ',
    manufacturer: '\u0085Based Hardware',
  });
  expect(
    firmwareLatestQuery({
      model: 'Omi Dev Kit',
      firmware: '1.2.3 ',
      hardware: '1',
      manufacturer: 'Based Hardware',
    }),
  ).toEqual({
    model: 'Omi Dev Kit',
    firmware: '1.2.3 ',
    hardware: '1',
    manufacturer: 'Based Hardware',
  });
  expect(
    firmwareLatestQuery({
      model: 'Omi Dev Kit',
      firmware: ' \t',
      hardware: '1',
      manufacturer: 'Based Hardware',
    }),
  ).toBeNull();
  expect(
    firmwareLatestQuery({
      model: 'Omi Dev Kit',
      firmware: '',
      hardware: '1',
      manufacturer: 'Based Hardware',
    }),
  ).toBeNull();
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
  expect(parseOmiLatestFirmware(JSON.stringify({version: ' \t'}))).toEqual({
    version: ' \t',
    draft: false,
    minVersion: null,
  });
  expect(parseOmiLatestFirmware(JSON.stringify({}))).toBeNull();
});

test('names Flutter FirmwareUpdate padded GET version instead of remapping to latest', () => {
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({version: '  1.3.0  ', min_version: '1.0.0'}),
    ),
  ).toEqual({
    version: '  1.3.0  ',
    draft: false,
    minVersion: '1.0.0',
  });
  expect(
    parseOmiLatestFirmware(JSON.stringify({version: '1.3.0 '})),
  ).toEqual({
    version: '1.3.0 ',
    draft: false,
    minVersion: null,
  });
  expect(
    parseOmiLatestFirmware(JSON.stringify({version: '\u00851.3.0'})),
  ).toEqual({
    version: '\u00851.3.0',
    draft: false,
    minVersion: null,
  });
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({version: '1.3.0', min_version: '  1.0.0  '}),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: '  1.0.0  ',
  });
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({version: '1.3.0', min_version: '1.0.0 '}),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: '1.0.0 ',
  });
  expect(
    parseOmiLatestFirmware(JSON.stringify({version: ''})),
  ).toEqual({
    version: '',
    draft: false,
    minVersion: null,
  });
});

test('names Flutter FirmwareUpdate empty GET changelog lines instead of omitting them', () => {
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({
        version: '1.3.0',
        changelog: ['Fixed BLE reconnect', '  ', 'Battery improvements'],
      }),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
    changelog: ['Fixed BLE reconnect', '  ', 'Battery improvements'],
  });
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({version: '1.3.0', changelog: [' \t']}),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
    changelog: [' \t'],
  });
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({version: '1.3.0', changelog: ['\u0085']}),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
    changelog: ['\u0085'],
  });
});

test('parses GET latest firmware changelog and omits production empty-string default', () => {
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({
        version: '1.3.0',
        changelog: ['Fixed BLE reconnect', '  ', 'Battery improvements'],
      }),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
    changelog: ['Fixed BLE reconnect', '  ', 'Battery improvements'],
  });
  expect(
    parseOmiLatestFirmware(JSON.stringify({version: '1.3.0', changelog: ''})),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
  });
  expect(
    parseOmiLatestFirmware(JSON.stringify({version: '1.3.0', changelog: []})),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
  });
  expect(
    parseOmiLatestFirmware(JSON.stringify({version: '1.3.0', changelog: [1]})),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
  });
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({
        version: '1.3.0',
        changelog: ['Fixed BLE reconnect', 1, 'Battery improvements'],
      }),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
    changelog: ['Fixed BLE reconnect', 'Battery improvements'],
  });
});

test('does not omit GET firmware version when changelog exceeds 32', () => {
  const changelog = Array.from(
    {length: 33},
    (_, index) => `Change ${index + 1}`,
  );
  expect(
    parseOmiLatestFirmware(JSON.stringify({version: '1.3.0', changelog})),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
    changelog,
  });
});

test('keeps GET firmware version when a changelog item exceeds 10000', () => {
  const longItem = 'C'.repeat(10001);
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({
        version: '1.3.0',
        changelog: ['Fixed BLE reconnect', longItem, 'Battery improvements'],
      }),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
    changelog: ['Fixed BLE reconnect', longItem, 'Battery improvements'],
  });
});

test('fails closed for malformed GET latest firmware', () => {
  expect(() => parseOmiLatestFirmware(JSON.stringify([]))).toThrow();
  expect(() => parseOmiLatestFirmware(JSON.stringify({version: 1}))).toThrow();
  expect(() =>
    parseOmiLatestFirmware(JSON.stringify({version: '1.3.0', draft: 'yes'})),
  ).toThrow();
  expect(() =>
    parseOmiLatestFirmware(JSON.stringify({version: '1.3.0', min_version: 1})),
  ).toThrow();
});

test('old firmware names Flutter FirmwareUpdate type-wrong GET zip_url instead of remapping to a Latest Version chip', () => {
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({
        version: '1.3.0',
        zip_url: 'https://example.test/fw.zip',
        min_app_version: '1.0.0',
        min_app_version_code: '100',
      }),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
  });
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({
        version: '1.3.0',
        zip_url: null,
        min_app_version: null,
        min_app_version_code: null,
      }),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
  });
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({
        version: '1.3.0',
        zip_url: '',
        min_app_version: '  1.0.0  ',
        min_app_version_code: '  100  ',
      }),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
  });
  for (const extra of [1, true, [], {}]) {
    expect(() =>
      parseOmiLatestFirmware(JSON.stringify({version: '1.3.0', zip_url: extra})),
    ).toThrow('Omi firmware is malformed');
    expect(() =>
      parseOmiLatestFirmware(
        JSON.stringify({version: '1.3.0', min_app_version: extra}),
      ),
    ).toThrow('Omi firmware is malformed');
    expect(() =>
      parseOmiLatestFirmware(
        JSON.stringify({version: '1.3.0', min_app_version_code: extra}),
      ),
    ).toThrow('Omi firmware is malformed');
  }
});

test('old firmware names Flutter FirmwareUpdate type-wrong GET ota_update_steps item instead of remapping to a Latest Version chip', () => {
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({
        version: '1.3.0',
        ota_update_steps: ['Connect device', 'Install'],
      }),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
  });
  expect(
    parseOmiLatestFirmware(JSON.stringify({version: '1.3.0'})),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
  });
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({version: '1.3.0', ota_update_steps: null}),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
  });
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({version: '1.3.0', ota_update_steps: 1}),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
  });
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({version: '1.3.0', ota_update_steps: []}),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
  });
  expect(
    parseOmiLatestFirmware(
      JSON.stringify({version: '1.3.0', ota_update_steps: ['']}),
    ),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: null,
  });
  for (const extra of [1, true, [], {}]) {
    expect(() =>
      parseOmiLatestFirmware(
        JSON.stringify({version: '1.3.0', ota_update_steps: [extra]}),
      ),
    ).toThrow('Omi firmware is malformed');
  }
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
  request.mockResolvedValueOnce({
    id: 'firmware',
    status: 200,
    body: JSON.stringify({version: '1.3.0', min_version: '1.0.0'}),
  });
  expect(
    await loadOmiLatestFirmware(backend, {
      model: '  Omi Dev Kit  ',
      firmware: '  1.2.3  ',
      hardware: '1 ',
      manufacturer: '\u0085Based Hardware',
    }),
  ).toEqual({
    version: '1.3.0',
    draft: false,
    minVersion: '1.0.0',
  });
  expect(request).toHaveBeenLastCalledWith({
    id: expect.any(String),
    method: 'GET',
    expectedApiContract: 'omi',
    path:
      `/v2/firmware/latest?device_model=${encodeURIComponent('  Omi Dev Kit  ')}` +
      `&firmware_revision=${encodeURIComponent('  1.2.3  ')}` +
      `&hardware_revision=${encodeURIComponent('1 ')}` +
      `&manufacturer_name=${encodeURIComponent('\u0085Based Hardware')}`,
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

test('old firmware names Flutter FirmwareUpdate type-wrong GET ota_update_steps item instead of empty latest', async () => {
  const request = jest.fn(async () => ({
    id: 'firmware',
    status: 200,
    body: JSON.stringify({version: '1.3.0', ota_update_steps: [1]}),
  }));
  const backend = {request} as unknown as OmiBackend;
  await expect(
    loadOmiLatestFirmware(backend, {
      model: 'Omi Dev Kit',
      firmware: '1.2.3',
      hardware: '1',
      manufacturer: 'Based Hardware',
    }),
  ).rejects.toThrow('Omi firmware is malformed');
});

test('old firmware names Flutter FirmwareUpdate type-wrong GET zip_url instead of empty latest', async () => {
  const request = jest.fn(async () => ({
    id: 'firmware',
    status: 200,
    body: JSON.stringify({version: '1.3.0', zip_url: 1}),
  }));
  const backend = {request} as unknown as OmiBackend;
  await expect(
    loadOmiLatestFirmware(backend, {
      model: 'Omi Dev Kit',
      firmware: '1.2.3',
      hardware: '1',
      manufacturer: 'Based Hardware',
    }),
  ).rejects.toThrow('Omi firmware is malformed');
});
