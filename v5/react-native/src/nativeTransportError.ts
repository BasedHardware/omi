// Native HTTP failures reach clients as opaque thrown values carrying a
// string `code` property. Both desktop reads and chat history classify those
// failures the same way; only the user-facing copy differs per client.
export function nativeTransportErrorKind(error: unknown): string | null {
  if (error === null || typeof error !== 'object') {
    return null;
  }
  const code = (error as {code?: unknown}).code;
  return typeof code === 'string' ? code : null;
}
