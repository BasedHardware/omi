'use server';
import { lookup } from 'dns/promises';
import { isIP } from 'net';
import uploadThumbnail from './upload-thumbnail';

const MAX_THUMBNAILS = 10;
const MAX_THUMBNAIL_BYTES = 10 * 1024 * 1024;
const MAX_REDIRECTS = 3;
const FETCH_TIMEOUT_MS = 10_000;

function isBlockedIpv4(ip: string): boolean {
  const parts = ip.split('.').map((part) => Number(part));
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part))) return true;
  const [a, b] = parts;
  if (a === 0) return true; // "this network"
  if (a === 10) return true; // RFC1918
  if (a === 127) return true; // loopback
  if (a === 169 && b === 254) return true; // link-local, incl. 169.254.169.254 metadata
  if (a === 172 && b >= 16 && b <= 31) return true; // RFC1918
  if (a === 192 && b === 168) return true; // RFC1918
  if (a === 192 && b === 0) return true; // IETF protocol assignments / 192.0.0.0/24
  if (a === 100 && b >= 64 && b <= 127) return true; // CGNAT
  if (a >= 224) return true; // multicast, reserved, broadcast
  return false;
}

function isBlockedIpv6(ip: string): boolean {
  const normalized = ip.toLowerCase().split('%')[0];
  if (normalized === '::' || normalized === '::1') return true; // unspecified, loopback
  // IPv4-mapped / IPv4-compatible addresses reuse the IPv4 rules.
  const mapped = normalized.match(/^::(?:ffff:(?:0{1,4}:)?)?(\d+\.\d+\.\d+\.\d+)$/);
  if (mapped) return isBlockedIpv4(mapped[1]);
  if (/^f[cd]/.test(normalized)) return true; // unique-local fc00::/7
  if (/^fe[89ab]/.test(normalized)) return true; // link-local fe80::/10
  if (normalized.startsWith('ff')) return true; // multicast
  if (normalized.startsWith('64:ff9b')) return true; // NAT64
  return false;
}

function isBlockedAddress(ip: string): boolean {
  const version = isIP(ip);
  if (version === 4) return isBlockedIpv4(ip);
  if (version === 6) return isBlockedIpv6(ip);
  return true;
}

/**
 * Reject anything that is not a plain https URL resolving exclusively to
 * public addresses. Guards the server action against being used as an SSRF
 * proxy into the VPC or the cloud metadata service.
 */
async function assertPublicHttpsUrl(rawUrl: string): Promise<URL> {
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    throw new Error('Thumbnail URL is not a valid URL');
  }

  if (url.protocol !== 'https:') {
    throw new Error('Thumbnail URL must use https');
  }
  if (url.username || url.password) {
    throw new Error('Thumbnail URL must not carry credentials');
  }

  const hostname = url.hostname.replace(/^\[|\]$/g, '');
  if (isIP(hostname)) {
    if (isBlockedAddress(hostname)) {
      throw new Error('Thumbnail URL resolves to a non-public address');
    }
    return url;
  }

  const resolved = await lookup(hostname, { all: true, verbatim: true });
  if (resolved.length === 0) {
    throw new Error('Thumbnail URL host does not resolve');
  }
  // Every answer must be public: a single private answer is enough for the
  // runtime to pick it.
  if (resolved.some((entry) => isBlockedAddress(entry.address))) {
    throw new Error('Thumbnail URL resolves to a non-public address');
  }
  return url;
}

/** Fetch following redirects manually so every hop is re-validated. */
async function fetchThumbnail(rawUrl: string): Promise<Response> {
  let target = rawUrl;

  for (let hop = 0; hop <= MAX_REDIRECTS; hop++) {
    const url = await assertPublicHttpsUrl(target);
    const response = await fetch(url, {
      redirect: 'manual',
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });

    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get('location');
      if (!location) {
        throw new Error('Thumbnail redirect is missing a Location header');
      }
      target = new URL(location, url).toString();
      continue;
    }

    if (!response.ok) {
      throw new Error(`Thumbnail fetch failed with status ${response.status}`);
    }
    return response;
  }

  throw new Error('Thumbnail fetch exceeded the redirect limit');
}

/** Read the body with a hard byte cap so a huge response can't exhaust memory. */
async function readCappedBlob(response: Response): Promise<Blob> {
  const declaredLength = Number(response.headers.get('content-length'));
  if (Number.isFinite(declaredLength) && declaredLength > MAX_THUMBNAIL_BYTES) {
    throw new Error('Thumbnail exceeds the maximum allowed size');
  }

  const body = response.body;
  if (!body) {
    throw new Error('Thumbnail response has no body');
  }

  const reader = body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_THUMBNAIL_BYTES) {
        throw new Error('Thumbnail exceeds the maximum allowed size');
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
    await body.cancel().catch(() => undefined);
  }

  return new Blob(chunks as BlobPart[], {
    type: response.headers.get('content-type') ?? 'application/octet-stream',
  });
}

export default async function uploadThumbnails(
  thumbnailUrls: string[],
  token: string,
): Promise<string[]> {
  const thumbnailIds: string[] = [];

  // The caller is untrusted: refuse to make any outbound request until a
  // credential is present.
  if (typeof token !== 'string' || !/^[\w-]+\.[\w-]+\.[\w-]+$/.test(token)) {
    console.warn('⚠️ [uploadThumbnails] Missing or malformed auth token');
    return thumbnailIds;
  }

  if (!Array.isArray(thumbnailUrls) || thumbnailUrls.length === 0) {
    return thumbnailIds;
  }

  if (thumbnailUrls.length > MAX_THUMBNAILS) {
    console.warn('⚠️ [uploadThumbnails] Too many thumbnail URLs supplied');
    return thumbnailIds;
  }

  console.log('📸 [uploadThumbnails] Uploading thumbnails...');

  for (const thumbnailUrl of thumbnailUrls) {
    try {
      if (typeof thumbnailUrl !== 'string') {
        continue;
      }
      const response = await fetchThumbnail(thumbnailUrl);
      const blob = await readCappedBlob(response);
      const thumbnailFormData = new FormData();
      thumbnailFormData.append('file', blob, 'thumbnail.jpg');

      const thumbnailResult = await uploadThumbnail(thumbnailFormData, token);

      if (thumbnailResult) {
        thumbnailIds.push(thumbnailResult.thumbnail_id);
        console.log(
          '📸 [uploadThumbnails] Thumbnail uploaded successfully:',
          thumbnailResult.thumbnail_id,
        );
      } else {
        console.warn('⚠️ [uploadThumbnails] Failed to upload thumbnail');
      }
    } catch (thumbnailError) {
      console.warn(
        '⚠️ [uploadThumbnails] Error uploading thumbnail, continuing:',
        thumbnailError,
      );
    }
  }

  console.log('📸 [uploadThumbnails] Thumbnail IDs collected:', thumbnailIds);
  return thumbnailIds;
}
