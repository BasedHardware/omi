/**
 * The per-client served-read counter.
 *
 * `apps/service/observability/served-count.ts` answers "how many domain reads
 * did this process actually serve?". This answers the strictly harder question
 * a launcher needs: "how many did the app **I** launched read?" — because a
 * global aggregate is satisfied by any stray client, and wave 9's whole lesson
 * is that a number nobody can join to a run proves nothing. `dev-stack.sh
 * --assert` joins on exactly this map, keyed by the `x-omi-client-id` header it
 * sends.
 *
 * It is recorded only AFTER a domain response body exists — never at dispatch.
 * A dispatch-side number may not appear in a verdict (swarm protocol §5):
 * "requests sent" and "requests served" are different questions, and a shell
 * once reported `servedCount=4 status=PASS` while the backend served zero.
 */

/** Sanitization for the per-client id. */
const CLIENT_ID_PATTERN = /^[A-Za-z0-9._:-]+$/;
const MAX_CLIENT_ID_LENGTH = 64;
const MAX_DISTINCT_CLIENT_KEYS = 64;
const ANONYMOUS_CLIENT_KEY = "anonymous";
const OVERFLOW_CLIENT_KEY = "overflow";

export interface ClientReadCounter {
  /** Records one SERVED domain read under the caller-supplied client id. */
  readonly record: (rawClientId: string | null | undefined) => void;
  readonly snapshot: () => Readonly<Record<string, number>>;
  readonly reset: () => void;
}

/**
 * Validates a raw `x-omi-client-id` header value. Rejects rather than mangles:
 * a too-long or off-charset id does not get truncated or stripped into a
 * DIFFERENT value that might collide with someone else's legitimate id — it is
 * simply treated as absent.
 */
export const sanitizeClientId = (rawClientId: string | null | undefined): string => {
  if (rawClientId === null || rawClientId === undefined || rawClientId === "") {
    return ANONYMOUS_CLIENT_KEY;
  }
  if (rawClientId.length > MAX_CLIENT_ID_LENGTH) {
    return ANONYMOUS_CLIENT_KEY;
  }
  if (!CLIENT_ID_PATTERN.test(rawClientId)) {
    return ANONYMOUS_CLIENT_KEY;
  }
  return rawClientId;
};

/**
 * The number of DISTINCT validated keys is capped. Once the cap is hit, an
 * unseen client id is counted under `"overflow"` rather than growing the map.
 * `"anonymous"` and `"overflow"` are fixed sentinels exempt from the cap
 * themselves (each is a single key, not attacker-multipliable), so the map's
 * worst case is `MAX_DISTINCT_CLIENT_KEYS + 2` — a client cycling ids every
 * request can only ever inflate the one `"overflow"` bucket.
 */
export const createClientReadCounter = (): ClientReadCounter => {
  const counts = new Map<string, number>();
  return Object.freeze({
    record(rawClientId: string | null | undefined): void {
      const sanitized = sanitizeClientId(rawClientId);
      const isSentinel = sanitized === ANONYMOUS_CLIENT_KEY;
      const key = isSentinel
        || counts.has(sanitized)
        || counts.size < MAX_DISTINCT_CLIENT_KEYS
        ? sanitized
        : OVERFLOW_CLIENT_KEY;
      counts.set(key, (counts.get(key) ?? 0) + 1);
    },
    snapshot: () => Object.freeze(Object.fromEntries(counts)),
    reset: () => { counts.clear(); },
  });
};
