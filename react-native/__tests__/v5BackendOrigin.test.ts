import {
  CLOUD_BACKEND_ORIGIN,
  LOCAL_BACKEND_ORIGIN,
  V5_BACKEND_URL_ENV,
  isCaptureBackendPath,
  resolveNativeRequestOrigin,
  validateLoopbackBackendUrl,
  validateV5BackendUrl,
} from '../src/v5BackendOrigin';

const workerOrigin = 'https://omi-v5-backend-staging.example.workers.dev';

test('allowlisted worker URL is used for device-session capture', () => {
  expect(validateV5BackendUrl(workerOrigin)?.origin).toBe(workerOrigin);
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/device-sessions',
      v5BackendUrl: workerOrigin,
    }),
  ).toEqual({ok: true, origin: workerOrigin});
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/device-sessions/11111111-2222-3333-4444-555555555555/audio',
      v5BackendUrl: workerOrigin,
    }),
  ).toEqual({ok: true, origin: workerOrigin});
  expect(V5_BACKEND_URL_ENV).toBe('OMI_V5_BACKEND_URL');
});

test('http and credentialed V5 URLs are rejected', () => {
  expect(
    validateV5BackendUrl('http://omi-v5-backend-staging.example.workers.dev'),
  ).toBeNull();
  expect(validateV5BackendUrl('http://127.0.0.1:8787')).toBeNull();
  expect(
    validateV5BackendUrl(
      'https://user:secret@omi-v5-backend-staging.example.workers.dev',
    ),
  ).toBeNull();
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/device-sessions',
      v5BackendUrl: 'http://omi-v5-backend-staging.example.workers.dev',
    }),
  ).toEqual({ok: false, reason: 'rejected'});
});

test('random hosts are rejected', () => {
  expect(validateV5BackendUrl('https://evil.example')).toBeNull();
  expect(validateV5BackendUrl('https://example.com')).toBeNull();
  expect(validateV5BackendUrl('https://workers.dev')).toBeNull();
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/device-sessions',
      v5BackendUrl: 'https://evil.example',
    }),
  ).toEqual({ok: false, reason: 'rejected'});
});

test('loopback still works for local backend and https V5', () => {
  expect(validateLoopbackBackendUrl(LOCAL_BACKEND_ORIGIN)?.origin).toBe(
    LOCAL_BACKEND_ORIGIN,
  );
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/device-sessions',
      localSelected: true,
      localBackendUrl: LOCAL_BACKEND_ORIGIN,
    }),
  ).toEqual({ok: true, origin: LOCAL_BACKEND_ORIGIN});
  expect(validateV5BackendUrl('https://127.0.0.1')?.origin).toBe(
    'https://127.0.0.1',
  );
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/device-sessions',
      v5BackendUrl: 'https://localhost',
    }),
  ).toEqual({ok: true, origin: 'https://localhost'});
});

test('old-cloud reads stay on api.omi.me when V5 is configured', () => {
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/settings',
      v5BackendUrl: workerOrigin,
    }),
  ).toEqual({ok: true, origin: CLOUD_BACKEND_ORIGIN});
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/conversations',
      v5BackendUrl: workerOrigin,
    }),
  ).toEqual({ok: true, origin: CLOUD_BACKEND_ORIGIN});
  expect(isCaptureBackendPath('/v1/device-sessions')).toBe(true);
  expect(isCaptureBackendPath('/v1/device-sessions-extra')).toBe(false);
  expect(isCaptureBackendPath('/v1/settings')).toBe(false);
});
