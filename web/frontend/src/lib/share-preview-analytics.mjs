/** Preview crawlers reveal the destination app in their user agent. Never send the raw value. */
export function previewDestination(userAgent) {
  const agent = String(userAgent || '').toLowerCase();
  if (/whatsapp/.test(agent)) return 'whatsapp';
  if (/telegram/.test(agent)) return 'telegram';
  if (/slack/.test(agent)) return 'slack';
  if (/discord/.test(agent)) return 'discord';
  if (/signal/.test(agent)) return 'signal';
  if (/teams|skype/.test(agent)) return 'microsoft';
  if (/linkedin/.test(agent)) return 'linkedin';
  if (/twitter|xbot/.test(agent)) return 'x';
  if (/facebookexternalhit|facebot|messenger/.test(agent)) return 'meta';
  if (/imessage|messages\//.test(agent)) return 'imessage';
  if (/googlebot|bingbot|applebot|duckduckbot|yandexbot/.test(agent)) return 'search';
  if (/reddit/.test(agent)) return 'reddit';
  if (/pinterest/.test(agent)) return 'pinterest';
  if (/bot|crawler|spider|preview|unfurl|embed|fetcher/.test(agent)) return 'other_bot';
  return null;
}

export function previewAttribution(searchParams) {
  const source = searchParams.get('s');
  const shareId = searchParams.get('sid');
  return {
    s: ['ios', 'android', 'mac', 'win', 'web'].includes(source) ? source : 'unknown',
    share_id: /^[a-zA-Z0-9_-]{8,64}$/.test(shareId || '') ? shareId : undefined,
  };
}

/** Capture only when the request has a known preview user agent. No person profile or IP enrichment. */
export async function capturePreviewRequest(userAgent, requestKind, searchParams) {
  const destination_app = previewDestination(userAgent);
  const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
  if (!destination_app || !key) return;
  const host = process.env.NEXT_PUBLIC_POSTHOG_HOST || 'https://us.i.posthog.com';
  try {
    await fetch(`${host}/capture/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: key,
        event: 'Share Preview Requested',
        distinct_id: crypto.randomUUID(),
        properties: {
          surface: 'conversation',
          request_kind: requestKind,
          destination_app,
          is_preview_bot: true,
          ...previewAttribution(searchParams),
          $process_person_profile: false,
          $geoip_disable: true,
        },
      }),
      signal: AbortSignal.timeout(750),
      cache: 'no-store',
      referrerPolicy: 'no-referrer',
    });
  } catch {
    // Preview rendering takes precedence over telemetry availability.
  }
}
