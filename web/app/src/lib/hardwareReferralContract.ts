export interface HardwareAttribution {
  campaign_id: 'omi_pocket_match_v1';
  state: 'attributed';
  checkout_url: string;
  discount_percent: 10;
}

export function safeHardwareCheckout(value: unknown): string | null {
  if (typeof value !== 'string' || /[\u0000-\u0020\u007f\\]/.test(value)) return null;
  try {
    const url = new URL(value);
    if (
      url.protocol !== 'https:' ||
      url.username ||
      url.password ||
      url.port ||
      !['www.omi.me', '88f4ed-c3.myshopify.com'].includes(url.hostname) ||
      !(url.pathname.startsWith('/checkouts/') || url.pathname.startsWith('/cart/'))
    )
      return null;
    return url.href;
  } catch {
    return null;
  }
}

export function parseHardwareAttribution(value: unknown): HardwareAttribution | null {
  if (typeof value !== 'object' || value === null) return null;
  const body = value as HardwareAttribution;
  const checkout = safeHardwareCheckout(body.checkout_url);
  return body.campaign_id === 'omi_pocket_match_v1' &&
    body.state === 'attributed' &&
    body.discount_percent === 10 &&
    checkout
    ? {
        campaign_id: body.campaign_id,
        state: body.state,
        discount_percent: 10,
        checkout_url: checkout,
      }
    : null;
}

export function isHardwareReferralCode(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.length <= 4096 &&
    /^ref2\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(value)
  );
}
