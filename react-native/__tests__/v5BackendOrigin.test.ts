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

test('an allowlisted stamp defaults a fresh install to the new plane', () => {
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
      softwarePlane: 'new',
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
      softwarePlane: 'new',
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
      softwarePlane: 'new',
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
      softwarePlane: 'new',
      v5BackendUrl: 'https://localhost',
    }),
  ).toEqual({ok: true, origin: 'https://localhost'});
});

test('old plane keeps every software path on api.omi.me', () => {
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/settings',
      softwarePlane: 'old',
      v5BackendUrl: workerOrigin,
    }),
  ).toEqual({ok: true, origin: CLOUD_BACKEND_ORIGIN});
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/conversations',
      softwarePlane: 'old',
      v5BackendUrl: workerOrigin,
    }),
  ).toEqual({ok: true, origin: CLOUD_BACKEND_ORIGIN});
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/chat-messages',
      softwarePlane: 'old',
      v5BackendUrl: workerOrigin,
    }),
  ).toEqual({ok: true, origin: CLOUD_BACKEND_ORIGIN});
  expect(
    resolveNativeRequestOrigin({
      path: '/v1/action-items',
      softwarePlane: 'new',
      v5BackendUrl: workerOrigin,
    }),
  ).toEqual({ok: true, origin: CLOUD_BACKEND_ORIGIN});
  expect(isCaptureBackendPath('/v1/device-sessions')).toBe(true);
  expect(isCaptureBackendPath('/v1/device-sessions-extra')).toBe(false);
  expect(isCaptureBackendPath('/v1/settings')).toBe(true);
  expect(isCaptureBackendPath('/v1/chat-messages')).toBe(true);
  expect(isCaptureBackendPath('/v1/conversations')).toBe(true);
  expect(isCaptureBackendPath('/v1/memories')).toBe(true);
  expect(isCaptureBackendPath('/v1/tasks')).toBe(true);
  expect(isCaptureBackendPath('/v1/apps')).toBe(false);
});
