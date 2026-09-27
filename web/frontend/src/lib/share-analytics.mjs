/** Only fixed, non-content dimensions are sent from public share pages. */
export function shareSurface(pathname) {
  if (/^\/(?:conversations|memories)\/[^/]+\/?$/.test(pathname)) return 'conversation';
  if (/^\/chat\/[^/]+\/?$/.test(pathname)) return 'chat';
  if (/^\/tasks\/[^/]+\/?$/.test(pathname)) return 'tasks';
  if (/^\/recaps\/[^/]+\/?$/.test(pathname)) return 'recap';
  if (/^\/apps\/[^/]+\/?$/.test(pathname)) return 'app';
  if (/^\/wrapped\/?$/.test(pathname)) return 'wrapped';
  if (/^\/unlimited\/?$/.test(pathname)) return 'unlimited';
  return null;
}

export function shareSource(value) {
  return ['ios', 'android', 'mac', 'win', 'web'].includes(value) ? value : 'unknown';
}

export function shareId(value) {
  return /^[a-zA-Z0-9_-]{8,64}$/.test(value || '') ? value : undefined;
}

export function deviceClass(userAgent) {
  if (/bot|crawl|spider|preview|slack|facebookexternalhit|whatsapp/i.test(userAgent))
    return 'bot';
  if (/ipad|tablet/i.test(userAgent)) return 'tablet';
  if (/iphone|ipod|android.*mobile/i.test(userAgent)) return 'mobile';
  if (/android/i.test(userAgent)) return 'tablet';
  return 'desktop';
}

export function ctaTarget(href) {
  if (!href) return null;
  if (/^omi:\/\//i.test(href) || /^intent:\/\//i.test(href)) return 'open_in_omi';
  try {
    const url = new URL(href, 'https://h.omi.me');
    if (url.hostname === 'apps.apple.com') return 'app_store';
    if (url.hostname === 'play.google.com') return 'play_store';
    if (url.hostname === 'omi.me' || url.hostname === 'www.omi.me') {
      if (/mac|download/i.test(url.pathname)) return 'mac';
      if (/products|shop|wearable|pendant/i.test(url.pathname)) return 'pendant';
      return 'omi_me';
    }
    if (/shop\.omi\.me$/.test(url.hostname)) return 'pendant';
  } catch {
    return null;
  }
  return null;
}

/** Add store and marketing attribution only to known outbound CTA destinations. */
export function attributedCtaHref(href, surface, source, sid) {
  const target = ctaTarget(href);
  if (!target) return href;
  if (target === 'open_in_omi') {
    if (!/^intent:\/\//i.test(href)) return href;
    return href.replace(/S\.browser_fallback_url=([^;]+)/, (whole, encoded) => {
      try {
        const fallback = decodeURIComponent(encoded);
        return `S.browser_fallback_url=${encodeURIComponent(
          attributedCtaHref(fallback, surface, source, sid),
        )}`;
      } catch {
        return whole;
      }
    });
  }
  const url = new URL(href, 'https://h.omi.me');
  const campaign = `share_${surface}`;
  if (target === 'app_store') {
    url.searchParams.set('ct', campaign);
  } else if (target === 'play_store') {
    const referrer = new URLSearchParams({
      utm_source: source,
      utm_medium: 'share',
      utm_campaign: campaign,
    });
    if (sid) referrer.set('sid', sid);
    url.searchParams.set('referrer', referrer.toString());
  } else {
    url.searchParams.set('utm_source', source);
    url.searchParams.set('utm_medium', 'share');
    url.searchParams.set('utm_campaign', campaign);
    if (sid) url.searchParams.set('utm_content', sid);
  }
  return url.toString();
}
