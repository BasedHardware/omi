/**
 * Build a backend API URL from path segments. Dynamic route params arrive
 * already decoded by Next.js — a share token read from `/tasks/a%2Fb` is the
 * string `a/b` — so interpolating params raw into a fetch URL misroutes the
 * request or corrupts the query. Encoding every segment keeps the wire URL
 * well-formed regardless of what the param contains. Kept as plain JS so
 * node:test can assert without a TS loader.
 *
 * @param {string | undefined | null} base API origin, e.g. envConfig.API_URL
 * @param {...string} segments path pieces; fixed prefixes pass unharmed
 * @returns {string} `${base}/${segments.map(encodeURIComponent).join('/')}`
 */
export function sharedApiUrl(base, ...segments) {
  const trimmed = String(base ?? '').replace(/\/+$/, '');
  const encoded = segments.map((segment) => encodeURIComponent(segment)).join('/');
  return `${trimmed}/${encoded}`;
}
