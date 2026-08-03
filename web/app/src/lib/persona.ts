/**
 * The user's persona — their public AI clone.
 *
 * The persona itself is served as an `App` by `/v1/personas`; these helpers
 * cover the presentation details the app record does not carry.
 */

/** Public page for a persona, hosted by the separate personas.omi.me app. */
export function personaPublicUrl(username: string): string {
  return `https://personas.omi.me/u/${encodeURIComponent(username)}`;
}

/**
 * Whether a persona is publicly reachable.
 *
 * A persona needs a username to have a URL at all, must not be marked private,
 * and only appears publicly once review has approved it.
 */
export function isPersonaPublic(persona: {
  username?: string;
  private?: boolean;
  approved?: boolean;
}): boolean {
  return Boolean(persona.username) && !persona.private && persona.approved === true;
}

/** Human-readable review state for a persona that is not yet public. */
export function personaStatusLabel(persona: {
  username?: string;
  private?: boolean;
  approved?: boolean;
}): string {
  if (isPersonaPublic(persona)) return 'Public';
  if (persona.private) return 'Private';
  if (!persona.approved) return 'Under review';
  return 'Not published';
}
