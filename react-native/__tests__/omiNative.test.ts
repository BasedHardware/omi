import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {
  resolveOmiBackend,
  resolveOmiNative,
  type NativeHttpRequest,
  type NativeHttpResponse,
  type OmiBackend,
  type OmiNative,
} from '../src/omiNative';

test('android scan keeps the connected device and serializes GATT writes', () => {
  const source = readFileSync(
    resolve(
      __dirname,
      '../android/app/src/main/java/com/rnruntime/OmiBleController.kt',
    ),
    'utf8',
  );
  expect(source).toContain('results[kept.id] = kept');
  expect(source).toContain('private val gattQueue');
  expect(source).toContain('enqueueGatt');
  expect(source).toContain('GattOp.Read');
  expect(source).toContain('GattOp.EnableNotify');
  expect(source).not.toContain(
    'if (codecChar != null) gatt.readCharacteristic(codecChar)',
  );
});

test('android registers a credential-bearing OmiBackend transport', () => {
  const backend = readFileSync(
    resolve(
      __dirname,
      '../android/app/src/main/java/com/rnruntime/OmiBackendModule.kt',
    ),
    'utf8',
  );
  const pack = readFileSync(
    resolve(
      __dirname,
      '../android/app/src/main/java/com/rnruntime/OmiNativePackage.kt',
    ),
    'utf8',
  );
  expect(backend).toContain('override fun getName() = "OmiBackend"');
  expect(backend).toContain('https://api.omi.me');
  expect(backend).toContain('OMI_LOCAL_API_TOKEN');
  expect(backend).toContain('OMI_LOCAL_API_CLIENT_ID');
  expect(backend).toContain('x-omi-client-id');
  expect(backend).toContain('Bearer ');
  expect(backend).not.toContain('workers.dev');
  expect(backend).toContain('Android generation streaming is unavailable');
  expect(pack).toContain('OmiBackendModule(reactContext)');
});

test('public native hardware surface does not advertise unimplemented adapters', () => {
  const source = require('node:fs').readFileSync(
    require('node:path').resolve(__dirname, '../src/omiNativeTypes.ts'),
    'utf8',
  );

  expect(source).not.toContain('readCharacteristic');
  expect(source).not.toContain('getWatchStatus');
  expect(source).not.toContain('capturePhoto');
  expect(source).not.toContain('startPhoneCall');
  expect(source).not.toContain('getWifiNetwork');
  expect(source).toContain('startScan');
  expect(source).toContain('connectDevice');
  expect(source).toContain('connectedDeviceId');
  expect(source).toContain('ConnectionPhase');
});

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

test('native HTTP contract exposes only an origin-relative request and normalized response', async () => {
  const captured: NativeHttpRequest[] = [];
  const nativeModule: OmiBackend = {
    request: async (
      request: NativeHttpRequest,
    ): Promise<NativeHttpResponse> => {
      captured.push(request);
      return {id: request.id, status: 200, body: '{"status":"ok"}'};
    },
    generationEvents: async () => ({id: 'events', status: 200, body: ''}),
    cancelGenerationEvents: async () => {},
  };
  const request: NativeHttpRequest = {
    id: 'request-1',
    method: 'POST',
    path: '/v1/chat-messages',
    headers: {'x-request-label': 'chat'},
    body: '{"text":"hello"}',
  };

  const selected = resolveOmiBackend(nativeModule);
  const response = await selected.adapter!.request(request);

  expect(captured).toEqual([request]);
  expect(Object.keys(captured[0]).sort()).toEqual([
    'body',
    'headers',
    'id',
    'method',
    'path',
  ]);
  expect(response).toEqual({
    id: 'request-1',
    status: 200,
    body: '{"status":"ok"}',
  });
  expect(selected.installed).toBe(true);
});
