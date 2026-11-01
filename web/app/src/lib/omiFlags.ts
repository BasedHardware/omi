import { getClientFlags } from '@/lib/api';
import type { ClientFlag, ClientFlagsResponse } from '@/lib/omiApi.generated';

/**
 * Omi flag store answers, fetched once per page load and read ahead of PostHog.
 * A key the store does not list, a failed fetch, or no answer within the timeout
 * is `undefined`, so the caller keeps PostHog's answer.
 */
let pending: Promise<Map<string, ClientFlag> | null> | null = null;

export function loadOmiFlags(
  load: () => Promise<ClientFlagsResponse> = getClientFlags,
): Promise<Map<string, ClientFlag> | null> {
  if (!pending) {
    const request = load()
      .then(
        (response) => new Map(response.flags.map((flag) => [flag.key, flag] as const)),
      )
      .catch(() => {
        if (pending === request) pending = null; // the next read retries
        return null;
      });
    pending = request;
  }
  return pending;
}

export async function omiFlagEnabled(
  key: string,
  {
    timeoutMs = 2000,
    load,
  }: { timeoutMs?: number; load?: () => Promise<ClientFlagsResponse> } = {},
): Promise<boolean | undefined> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<null>((resolve) => {
    timer = setTimeout(() => resolve(null), timeoutMs);
  });
  try {
    const flags = await Promise.race([loadOmiFlags(load), timeout]);
    return flags?.get(key)?.enabled;
  } finally {
    clearTimeout(timer);
  }
}

/** Account change: the next read fetches the new account's answers. */
export function resetOmiFlags(): void {
  pending = null;
}
