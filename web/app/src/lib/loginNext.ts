/**
 * Where sign-in returns to. `/login?next=/conversations?id=abc` lets a link
 * from outside the app (an h.omi.me item link, a protected page) land on that
 * page after sign-in instead of Home.
 *
 * Only same-origin app paths are accepted: a `next` that could leave the app
 * (`//evil.example`, `https://…`, `/\evil`) or loop back to login falls back
 * to Home.
 */
export const DEFAULT_AFTER_LOGIN = '/home';

export function safeNextPath(raw: string | null | undefined): string {
  if (!raw) return DEFAULT_AFTER_LOGIN;
  const value = raw.trim();
  if (!value.startsWith('/') || value.startsWith('//') || value.includes('\\')) {
    return DEFAULT_AFTER_LOGIN;
  }
  // Control characters can smuggle a scheme past the checks above in some parsers.
  if (/[\u0000-\u001f\u007f]/.test(value)) return DEFAULT_AFTER_LOGIN;
  let url: URL;
  try {
    url = new URL(value, 'https://app.invalid');
  } catch {
    return DEFAULT_AFTER_LOGIN;
  }
  if (url.origin !== 'https://app.invalid') return DEFAULT_AFTER_LOGIN;
  if (url.pathname === '/login' || url.pathname.startsWith('/login/'))
    return DEFAULT_AFTER_LOGIN;
  return `${url.pathname}${url.search}${url.hash}`;
}

/** The login URL that returns to [path] after sign-in. */
export function loginUrlReturningTo(path: string): string {
  const next = safeNextPath(path);
  return next === DEFAULT_AFTER_LOGIN
    ? '/login'
    : `/login?next=${encodeURIComponent(next)}`;
}
