/** Canonical Omi hardware branding for h.omi.me app-store surfaces (banners, CTAs, JSON-LD). */
export const APP_STORE_HARDWARE_PRODUCT = {
  name: 'Omi',
  displayPrice: '$89',
  schemaPrice: '89',
  currency: 'USD',
  description: 'AI-powered wearable. Real-time AI voice assistant.',
  storeUrl: 'https://www.omi.me/',
  marketplaceOrderUrl:
    'https://www.omi.me/?ref=omi_marketplace&utm_source=h.omi.me&utm_campaign=omi_marketplace_app_detail_page',
  shipping: 'Ships Worldwide',
  images: {
    primary: '/omi_1.webp',
    secondary: '/omi_2.webp',
  },
} as const;
