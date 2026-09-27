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
      return /mac|download/i.test(url.pathname) ? 'mac' : 'omi_me';
    }
    if (/shop\.omi\.me$/.test(url.hostname)) return 'pendant';
  } catch {
    return null;
  }
  return null;
}
