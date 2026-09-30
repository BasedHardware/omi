'use server';
import envConfig from '@/src/constants/envConfig';
import { SharedScreenFrameSet } from '@/src/types/memory.types';
import { sharedApiUrl } from '@/src/lib/shared-api-url.mjs';

export type SharedScreenshotsResult =
  | { ok: true; set: SharedScreenFrameSet }
  | { ok: false };

/**
 * The public screenshot set for a shared conversation. Never cached: every
 * response carries signed URLs that expire after 60 minutes, so a cached
 * copy would serve dead images.
 *
 * Failure (network, non-2xx, unparseable body) is `{ ok: false }`, distinct
 * from a successful empty set: a client renewing URLs keeps what it has and
 * retries on failure, and clears only on a successful empty response.
 */
export default async function getSharedScreenshots(
  id: string,
): Promise<SharedScreenshotsResult> {
  try {
    const response = await fetch(
      sharedApiUrl(envConfig.API_URL, 'v1', 'conversations', id, 'shared', 'screenshots'),
      { cache: 'no-store' },
    );
    if (!response.ok) return { ok: false };
    const set = (await response.json()) as SharedScreenFrameSet | null;
    if (!set || typeof set !== 'object') return { ok: false };
    return { ok: true, set };
  } catch {
    return { ok: false };
  }
}
