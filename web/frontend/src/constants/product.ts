export const PRODUCT_CONFIG = {
  name: 'Omi',
  price: '89',
  currency: 'USD',
  storeUrl: 'https://www.omi.me/',
  productUrl: 'https://www.omi.me/products/omi-dev-kit-2',
  appStoreUrl: 'https://apps.apple.com/us/app/friend-ai-wearable/id6502156163',
  playStoreUrl: 'https://play.google.com/store/apps/details?id=com.friend.ios',
  getPlatformLink(userAgent: string, token?: string, route?: 'chat' | 'tasks'): string {
    const isAndroid = /android/i.test(userAgent);
    const isIOS = /iphone|ipad|ipod/i.test(userAgent);

    if (isAndroid) {
      if (route === 'chat' && token) {
        return `intent://h.omi.me/chat/${token}#Intent;scheme=https;package=com.friend.ios;S.browser_fallback_url=${encodeURIComponent(
          PRODUCT_CONFIG.playStoreUrl,
        )};end`;
      }
      if (route === 'tasks' && token) {
        return `intent://h.omi.me/tasks/${token}#Intent;scheme=https;package=com.friend.ios;S.browser_fallback_url=${encodeURIComponent(
          PRODUCT_CONFIG.playStoreUrl,
        )};end`;
      }
      return PRODUCT_CONFIG.playStoreUrl;
    }

    if (isIOS) {
      if (route === 'chat' && token) {
        return `omi://h.omi.me/chat/${token}`;
      }
      if (route === 'tasks' && token) {
        return `omi://h.omi.me/tasks/${token}`;
      }
      return PRODUCT_CONFIG.appStoreUrl;
    }

    return PRODUCT_CONFIG.storeUrl;
  },
} as const;
