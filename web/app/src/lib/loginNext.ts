/**
 * Where sign-in returns to. `/login?next=/conversations?id=abc` lets a link
 * from outside the app (an h.omi.me item link, a protected page) land on that
 * page after sign-in instead of Home.
 *
 * Only same-origin app paths are accepted: a `next` that could leave the app
 * (`//evil.example`, `https://…`, `/\evil`, or a path that normalizes into one
 * such as `/.//evil.example`) or loop back to login falls back to Home.
 */
export const DEFAULT_AFTER_LOGIN = '/home';

const CONTROL_CHARS = /[\u0000-\u001f\u007f]/;

/** A path the router must not be allowed to treat as another origin. */
function leavesTheApp(path: string): boolean {
  return (
    !path.startsWith('/') ||
    path.startsWith('//') ||
    path.includes('\\') ||
    CONTROL_CHARS.test(path)
  );
}

function isLoginPath(path: string): boolean {
  const pathname = path.split(/[?#]/, 1)[0] ?? '';
  return pathname === '/login' || pathname.startsWith('/login/');
}

/**
 * True when [path] is still a same-origin app path after the browser's own
 * normalization. `/.//evil.example` and `/%2f%2fevil.example` both become a
 * protocol-relative URL once a parser resolves them.
 */
function isSameOriginReturn(path: string): boolean {
  if (leavesTheApp(path) || isLoginPath(path)) return false;
  let decoded: string;
  try {
    decoded = decodeURIComponent(path);
  } catch {
    return false;
  }
  if (leavesTheApp(decoded) || isLoginPath(decoded)) return false;
  try {
    const again = new URL(decoded, 'https://app.invalid');
    if (again.origin !== 'https://app.invalid') return false;
    const normalized = `${again.pathname}${again.search}${again.hash}`;
    return !leavesTheApp(normalized) && !isLoginPath(normalized);
  } catch {
    return false;
  }
}

export function safeNextPath(raw: string | null | undefined): string {
  if (!raw) return DEFAULT_AFTER_LOGIN;
  const value = raw.trim();
  if (leavesTheApp(value)) return DEFAULT_AFTER_LOGIN;
  let url: URL;
  try {
    url = new URL(value, 'https://app.invalid');
  } catch {
    return DEFAULT_AFTER_LOGIN;
  }
  if (url.origin !== 'https://app.invalid') return DEFAULT_AFTER_LOGIN;
  const next = `${url.pathname}${url.search}${url.hash}`;
  if (!isSameOriginReturn(next)) return DEFAULT_AFTER_LOGIN;
  return next;
}

/** The login URL that returns to [path] after sign-in. */
export function loginUrlReturningTo(path: string): string {
  const next = safeNextPath(path);
  return next === DEFAULT_AFTER_LOGIN
    ? '/login'
    : `/login?next=${encodeURIComponent(next)}`;
}
