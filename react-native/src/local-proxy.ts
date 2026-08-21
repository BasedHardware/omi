export const LOCAL_PROXY_PREFIX = '/__omi/api';

export const DEV_BACKEND_SELECTOR = 'OMI_DEV_BACKEND';

const developmentBackendOrigins = {
  'example-platform': 'http://127.0.0.1:4851',
} as const;

export const DEVELOPMENT_BACKEND_UNSUPPORTED_STATUS = 503;

export const developmentBackendUnsupportedResponse = JSON.stringify({
  error: {
    code: 'development_backend_unsupported',
    retryable: false,
    action: 'none',
  },
});

const forbiddenHeaders = new Set([
  'authorization',
  'cookie',
  'proxy-authorization',
  'x-omi-client-id',
  'x-omi-contract-version',
]);

function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.replace(/^\[|\]$/g, '').toLocaleLowerCase();
  return (
    normalized === 'localhost' ||
    normalized === '127.0.0.1' ||
    normalized === '::1'
  );
}

export function assertLoopbackBackendUrl(value: string): URL {
  const url = new URL(value);
  if (
    (url.protocol !== 'http:' && url.protocol !== 'https:') ||
    !isLoopbackHostname(url.hostname) ||
    url.username !== '' ||
    url.password !== '' ||
    url.pathname !== '/' ||
    url.search !== '' ||
    url.hash !== ''
  ) {
    throw new Error(
      'OMI_LOCAL_BACKEND_URL must be a loopback origin without credentials',
    );
  }
  return url;
}

export function resolveLocalBackendUrl(
  environment: Record<string, string | undefined>,
): URL {
  const selection = environment[DEV_BACKEND_SELECTOR]?.trim();
  if (selection === undefined || selection === '') {
    return assertLoopbackBackendUrl(
      environment.OMI_LOCAL_BACKEND_URL ?? 'http://127.0.0.1:8787',
    );
  }
  if (environment.NODE_ENV === 'production') {
    throw new Error(`${DEV_BACKEND_SELECTOR} is unavailable in production`);
  }
  if (environment.OMI_LOCAL_BACKEND_URL?.trim()) {
    throw new Error(
      `${DEV_BACKEND_SELECTOR} cannot be combined with OMI_LOCAL_BACKEND_URL`,
    );
  }
  if (!(selection in developmentBackendOrigins)) {
    throw new Error(
      `${DEV_BACKEND_SELECTOR} must name a compatible allowlisted backend`,
    );
  }
  return new URL(
    developmentBackendOrigins[
      selection as keyof typeof developmentBackendOrigins
    ],
  );
}

export function isExamplePlatformSelection(
  environment: Record<string, string | undefined>,
): boolean {
  return environment[DEV_BACKEND_SELECTOR]?.trim() === 'example-platform';
}

export function isExamplePlatformRequestSupported(
  method: string | undefined,
  path: string | undefined,
): boolean {
  if (method !== 'GET' || path === undefined) {
    return false;
  }
  const url = new URL(assertLocalProxyPath(path), 'http://127.0.0.1');
  const backendPath = rewriteLocalProxyPath(`${url.pathname}${url.search}`);
  const backendUrl = new URL(backendPath, 'http://127.0.0.1');
  return (
    backendUrl.pathname === '/v1/conversations' ||
    backendUrl.pathname === '/v1/memories'
  );
}

export function assertLocalProxyPath(path: string): string {
  if (!path.startsWith('/') || path.startsWith('//')) {
    throw new Error('local proxy paths must be origin-relative');
  }
  const url = new URL(path, 'http://omi.local');
  if (
    url.origin !== 'http://omi.local' ||
    (url.pathname !== LOCAL_PROXY_PREFIX &&
      !url.pathname.startsWith(`${LOCAL_PROXY_PREFIX}/`))
  ) {
    throw new Error('local proxy paths must stay under the local API prefix');
  }
  return `${url.pathname}${url.search}`;
}

export function rewriteLocalProxyPath(path: string): string {
  const safePath = assertLocalProxyPath(path);
  const rewritten = safePath.slice(LOCAL_PROXY_PREFIX.length);
  return rewritten === '' ? '/' : rewritten;
}

export function localProxyRequestInit(init: RequestInit = {}): RequestInit {
  const headers = new Headers(init.headers);
  headers.forEach((_value, name) => {
    if (forbiddenHeaders.has(name.toLocaleLowerCase())) {
      throw new Error(`browser requests cannot set ${name}`);
    }
  });
  if (init.body !== undefined && init.body !== null) {
    headers.set('content-type', 'application/json');
  }
  return {...init, credentials: 'omit', headers};
}
