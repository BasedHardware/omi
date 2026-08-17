/**
 * Resolves whether this build may talk to a local Firebase Auth emulator.
 *
 * Two independent conditions must hold, so a stray env var in a production
 * deploy cannot silently redirect real sign-in at an unreachable host:
 * the build must not be a production build, and the configured host must be
 * loopback. Anything else resolves to null and the app uses real Firebase.
 */
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]', '::1']);

export function resolveAuthEmulatorUrl(env = {}) {
  if (env.NODE_ENV === 'production') return null;

  const raw = (env.NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST ?? '').trim();
  if (!raw) return null;

  const withoutScheme = raw.replace(/^https?:\/\//, '').replace(/\/+$/, '');
  const separator = withoutScheme.lastIndexOf(':');
  if (separator <= 0) return null;

  const host = withoutScheme.slice(0, separator);
  const port = withoutScheme.slice(separator + 1);
  if (!LOOPBACK_HOSTS.has(host)) return null;
  if (!/^\d+$/.test(port)) return null;

  return `http://${host}:${port}`;
}
