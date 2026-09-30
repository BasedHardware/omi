'use server';
import envConfig from '@/src/constants/envConfig';
import { SharedScreenFrameSet } from '@/src/types/memory.types';
import { sharedApiUrl } from '@/src/lib/shared-api-url.mjs';

/**
 * The public screenshot set for a shared conversation. Never cached: every
 * response carries signed URLs that expire after 60 minutes, so a cached
 * copy would serve dead images. Returns null on any failure — the page then
 * hides the strip rather than showing an error.
 */
export default async function getSharedScreenshots(
  id: string,
): Promise<SharedScreenFrameSet | null> {
  try {
    const response = await fetch(
      sharedApiUrl(envConfig.API_URL, 'v1', 'conversations', id, 'shared', 'screenshots'),
      { cache: 'no-store' },
    );
    if (!response.ok) return null;
    return (await response.json()) as SharedScreenFrameSet;
  } catch {
    return null;
  }
}
