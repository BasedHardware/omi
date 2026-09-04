export const CLOUD_BACKEND_ORIGIN = 'https://api.omi.me';
export const LOCAL_BACKEND_ORIGIN = 'http://127.0.0.1:8787';
export const V5_BACKEND_URL_ENV = 'OMI_V5_BACKEND_URL';

type ParsedOrigin = {
  hostname: string;
  origin: string;
  port: string;
  protocol: 'http:' | 'https:';
};

function parseOrigin(value: string): ParsedOrigin | null {
  const match = /^(https?):\/\/(\[[^\]]+\]|[^:/?#@]+)(?::([0-9]+))?\/?$/i.exec(
    value,
  );
  if (match === null || match[0] !== value) {
    return null;
  }
  const protocol = `${match[1].toLocaleLowerCase()}:` as 'http:' | 'https:';
  const rawHostname = match[2];
  const hostname = rawHostname.replace(/^\[|\]$/g, '').toLocaleLowerCase();
  if (
    (rawHostname.startsWith('[') && hostname !== '::1') ||
    (!rawHostname.startsWith('[') && !/^[a-z0-9.-]+$/.test(hostname))
  ) {
    return null;
  }
  const rawPort = match[3] ?? '';
  const portNumber = rawPort === '' ? null : Number(rawPort);
  if (
    (portNumber !== null &&
      (!Number.isInteger(portNumber) ||
        portNumber < 1 ||
        portNumber > 65535)) ||
    hostname.length === 0
  ) {
    return null;
  }
  const port =
    (protocol === 'https:' && portNumber === 443) ||
    (protocol === 'http:' && portNumber === 80)
      ? ''
      : rawPort;
  const host = rawHostname.startsWith('[') ? `[${hostname}]` : hostname;
  return {
    hostname,
    origin: `${protocol}//${host}${port === '' ? '' : `:${port}`}`,
    port,
    protocol,
  };
}

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
  const route = path.split(/[?#]/, 1)[0];
  return (
    route === '/v1/settings' ||
    route === '/v1/chat-messages' ||
    route.startsWith('/v1/chat-generations/') ||
    route === '/v1/chat-attachments' ||
    route.startsWith('/v1/chat-attachments/') ||
    route === '/v1/device-sessions' ||
    route.startsWith('/v1/device-sessions/') ||
    route === '/v1/conversations' ||
    route === '/v1/memories' ||
    route === '/v1/tasks'
  );
}

export function validateV5BackendUrl(value: string): ParsedOrigin | null {
  const url = parseOrigin(value);
  if (
    url === null ||
    url.protocol !== 'https:' ||
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

export function validateLoopbackBackendUrl(value: string): ParsedOrigin | null {
  const url = parseOrigin(value);
  if (
    url === null ||
    (url.protocol !== 'http:' && url.protocol !== 'https:') ||
    !isLoopbackHostname(url.hostname)
  ) {
    return null;
  }
  return url;
}

export type NativeOriginResolution =
  | {ok: true; origin: string}
  | {ok: false; reason: 'rejected' | 'unconfigured'};

export type SoftwarePlane = 'old' | 'new';
export const SOFTWARE_PLANE_DEFAULTS_KEY = 'omi.backend.softwarePlane';

export function parseSoftwarePlane(value: unknown): SoftwarePlane {
  return value === 'new' ? 'new' : 'old';
}

export function resolveNativeRequestOrigin(input: {
  path: string;
  v5BackendUrl?: string;
  localBackendUrl?: string;
  localSelected?: boolean;
  softwarePlane?: SoftwarePlane;
}): NativeOriginResolution {
  if (input.localSelected) {
    const local = validateLoopbackBackendUrl(
      input.localBackendUrl ?? LOCAL_BACKEND_ORIGIN,
    );
    return local === null
      ? {ok: false, reason: 'rejected'}
      : {ok: true, origin: local.origin};
  }
  const stamped =
    input.v5BackendUrl === undefined
      ? null
      : validateV5BackendUrl(input.v5BackendUrl);
  const softwarePlane =
    input.softwarePlane ?? (stamped === null ? 'old' : 'new');
  if (parseSoftwarePlane(softwarePlane) === 'new') {
    if (input.v5BackendUrl === undefined || input.v5BackendUrl.length === 0) {
      return {ok: true, origin: CLOUD_BACKEND_ORIGIN};
    }
    if (stamped === null) {
      return {ok: false, reason: 'rejected'};
    }
    if (isCaptureBackendPath(input.path)) {
      return {ok: true, origin: stamped.origin};
    }
  }
  return {ok: true, origin: CLOUD_BACKEND_ORIGIN};
}
