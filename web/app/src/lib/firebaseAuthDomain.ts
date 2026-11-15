/** Production serves Firebase's helper through its own server, avoiding
 * third-party iframe storage. Local previews keep their configured domain.
 */
export function firebaseAuthDomain(
  configured: string | undefined,
  hostname: string,
): string | undefined {
  return hostname === 'app.omi.me' && configured?.endsWith('.firebaseapp.com')
    ? hostname
    : configured;
}
