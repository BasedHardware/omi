export const CLOUD_BACKEND_ORIGIN = 'https://api.omi.me';
export const LOCAL_BACKEND_ORIGIN = 'http://127.0.0.1:8787';
export const V5_BACKEND_URL_ENV = 'OMI_V5_BACKEND_URL';

export function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.replace(/^\[|\]$/g, '').toLocaleLowerCase();
  return (
    normalized === 'localhost' ||
    normalized === '127.0.0.1' ||
    normalized === '::1'
  );
}

export function isCloudHostname(hostname: string): boolean {
  return hostname.toLocaleLowerCase() === 'api.omi.me';
}

export function isAllowedV5Hostname(hostname: string): boolean {
  const normalized = hostname.replace(/^\[|\]$/g, '').toLocaleLowerCase();
  if (isLoopbackHostname(normalized) || isCloudHostname(normalized)) {
    return true;
  }
  return (
    normalized.endsWith('.workers.dev') &&
    normalized.length > '.workers.dev'.length
  );
}

export function isCaptureBackendPath(path: string): boolean {
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('://')) {
    return false;
  }
  const route = new URL(path, 'https://omi.invalid').pathname;
  return (
    route === '/v1/device-sessions' || route.startsWith('/v1/device-sessions/')
  );
}

export function validateV5BackendUrl(value: string): URL | null {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if (
    url.protocol !== 'https:' ||
    url.username !== '' ||
    url.password !== '' ||
    (url.pathname !== '' && url.pathname !== '/') ||
    url.search !== '' ||
    url.hash !== '' ||
    url.hostname.length === 0 ||
    !isAllowedV5Hostname(url.hostname)
  ) {
    return null;
  }
  if (
    !isLoopbackHostname(url.hostname) &&
    url.port !== '' &&
    url.port !== '443'
  ) {
    return null;
  }
  return url;
}

export function validateLoopbackBackendUrl(value: string): URL | null {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if (
    (url.protocol !== 'http:' && url.protocol !== 'https:') ||
    url.username !== '' ||
    url.password !== '' ||
    (url.pathname !== '' && url.pathname !== '/') ||
    url.search !== '' ||
    url.hash !== '' ||
    !isLoopbackHostname(url.hostname)
  ) {
    return null;
  }
  return url;
}

export type NativeOriginResolution =
  | {ok: true; origin: string}
  | {ok: false; reason: 'rejected' | 'unconfigured'};

export function resolveNativeRequestOrigin(input: {
  path: string;
  v5BackendUrl?: string;
  localBackendUrl?: string;
  localSelected?: boolean;
}): NativeOriginResolution {
  if (input.localSelected) {
    const local = validateLoopbackBackendUrl(
      input.localBackendUrl ?? LOCAL_BACKEND_ORIGIN,
    );
    return local === null
      ? {ok: false, reason: 'rejected'}
      : {ok: true, origin: local.origin};
  }
  if (isCaptureBackendPath(input.path) && input.v5BackendUrl !== undefined) {
    if (input.v5BackendUrl.length === 0) {
      return {ok: false, reason: 'unconfigured'};
    }
    const v5 = validateV5BackendUrl(input.v5BackendUrl);
    return v5 === null
      ? {ok: false, reason: 'rejected'}
      : {ok: true, origin: v5.origin};
  }
  return {ok: true, origin: CLOUD_BACKEND_ORIGIN};
}
