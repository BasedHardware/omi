const WEB_DEVICE_ID_KEY = 'omi-web-device-id';

/** Return the stable browser hash used for notifications and provenance. */
export async function getWebDeviceIdHash(): Promise<string | null> {
  if (typeof window === 'undefined') return null;

  let deviceId = localStorage.getItem(WEB_DEVICE_ID_KEY);
  if (!deviceId) {
    deviceId = `web_${Date.now()}_${Math.random().toString(36).substring(2, 15)}`;
    localStorage.setItem(WEB_DEVICE_ID_KEY, deviceId);
  }

  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(deviceId),
  );
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
    .slice(0, 8);
}
