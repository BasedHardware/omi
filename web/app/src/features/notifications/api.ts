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
export async function registerFCMToken(fcmToken: string): Promise<void> {
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const deviceIdHash = await getWebDeviceIdHash();
  if (!deviceIdHash) return;

  await fetchWithAuth('/v1/users/fcm-token', {
    method: 'POST',
    headers: {
      'X-App-Platform': 'web',
      'X-Device-Id-Hash': deviceIdHash,
    },
    body: JSON.stringify({
      fcm_token: fcmToken,
      time_zone: timeZone,
    }),
  });
}

/**
 * Unregister FCM token (called on sign out)
 * @param fcmToken - The FCM registration token to remove
 */
export async function unregisterFCMToken(fcmToken: string): Promise<void> {
  try {
    const deviceIdHash = await getWebDeviceIdHash();
    if (!deviceIdHash) return;

    await fetchWithAuth('/v1/users/fcm-token', {
      method: 'DELETE',
      headers: {
        'X-App-Platform': 'web',
        'X-Device-Id-Hash': deviceIdHash,
      },
      body: JSON.stringify({
        fcm_token: fcmToken,
      }),
    });
  } catch (error) {
    // Silently fail on logout - token cleanup is best-effort
    console.warn('Failed to unregister FCM token:', error);
  }
}
