/** Public share-link base URL for self-hosting (#4339). Matches backend OMI_SHARE_BASE_URL. */

const DEFAULT_SHARE_BASE = 'https://h.omi.me'

export function shareBaseUrl(
  raw: string | undefined = import.meta.env.VITE_OMI_SHARE_BASE_URL as string | undefined
): string {
  let value = (raw ?? '').trim()
  if (!value) value = DEFAULT_SHARE_BASE
  if (!value.includes('://')) value = `https://${value}`
  try {
    const parsed = new URL(value)
    if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname)
      return DEFAULT_SHARE_BASE
  } catch {
    return DEFAULT_SHARE_BASE
  }
  return value.replace(/\/+$/, '')
}

export function conversationShareUrl(
  id: string,
  raw?: string | undefined,
  sid: string = newShareId()
): string {
  const url = new URL(`${shareBaseUrl(raw)}/conversations/${id}`)
  url.searchParams.set('sid', sid)
  // The same Electron code also ships on Linux; avoid claiming those shares came from Windows.
  if (typeof navigator === 'undefined' || !/linux/i.test(navigator.userAgent)) {
    url.searchParams.set('s', 'win')
  }
  return url.toString()
}

/** Ephemeral link ID, independent of the sender and conversation. */
export function newShareId(): string {
  return crypto.randomUUID().replaceAll('-', '')
}
