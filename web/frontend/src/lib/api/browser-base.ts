import envConfig from '@/src/constants/envConfig';

/**
 * Base URL for requests issued from the browser.
 *
 * `API_URL` is not a `NEXT_PUBLIC_*` variable, so Next.js never inlines it into
 * the client bundle. A browser module reading it gets `undefined` and every
 * request degrades to a relative path against the web origin, which is not the
 * backend — the requests 404 against Next in production. Client modules must
 * read the public variable; the server-only value remains a fallback so a
 * component rendered on the server still resolves an absolute URL.
 */
export function browserApiBase(): string {
  return (envConfig.PUBLIC_API_URL ?? envConfig.API_URL ?? '').replace(/\/$/, '');
}
