import { getIdToken } from '@/lib/firebase';
import { getWebDeviceIdHash } from '@/lib/clientDevice';
import {
  invalidateCache,
  invalidationPatterns,
  fetchWithCache,
  cacheKeys,
  CACHE_TTL,
} from '@/lib/cache';
import {
  API_BASE_URL,
  fetchAuthorizedBlob,
  fetchWithAuth,
  getAudioAuthHeaders,
} from '@/shared/api/client';
import type { FairUseStatusResponse } from '@/lib/omiApi.generated';

export type FairUseStatus = Omit<FairUseStatusResponse, 'stage'> & {
  stage: 'none' | 'warning' | 'throttle' | 'restrict';
};

export async function getFairUseStatus(): Promise<FairUseStatus | null> {
  try {
    return await fetchWithAuth<FairUseStatus>('/v1/fair-use/status');
  } catch (error) {
    console.error('getFairUseStatus error:', error);
    return null;
  }
}
