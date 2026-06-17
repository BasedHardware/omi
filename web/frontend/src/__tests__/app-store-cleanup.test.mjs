import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

// Helper to read file content relative to project root
function readFile(relativePath) {
  let normalizedPath = relativePath;
  const normalizedCwd = process.cwd().replace(/\\/g, '/');
  if (
    normalizedCwd.endsWith('web/frontend') &&
    relativePath.startsWith('web/frontend/')
  ) {
    normalizedPath = relativePath.slice('web/frontend/'.length);
  }
  const filePath = path.join(process.cwd(), normalizedPath);
  return fs.readFileSync(filePath, 'utf8');
}

describe('Omi Store & Link Cleanup Validation', () => {
  describe('web/frontend/src/constants/product.ts', () => {
    it('defines PRODUCT_CONFIG constants correctly', () => {
      const content = readFile('web/frontend/src/constants/product.ts');
      assert.ok(content.includes("name: 'Omi'"), 'Name should be Omi');
      assert.ok(content.includes("price: '89'"), 'Price should be 89');
      assert.ok(
        content.includes("storeUrl: 'https://www.omi.me/'"),
        'Store URL should be correct',
      );
      assert.ok(
        content.includes("productUrl: 'https://www.omi.me/products/omi-dev-kit-2'"),
        'Product URL should be correct',
      );
      assert.ok(
        content.includes(
          "appStoreUrl: 'https://apps.apple.com/us/app/friend-ai-wearable/id6502156163'",
        ),
        'App Store URL should be correct',
      );
      assert.ok(
        content.includes(
          "playStoreUrl: 'https://play.google.com/store/apps/details?id=com.friend.ios'",
        ),
        'Play Store URL should be correct',
      );
    });

    it('contains getPlatformLink routing logic for iOS, Android, and desktop', () => {
      const content = readFile('web/frontend/src/constants/product.ts');
      assert.ok(
        content.includes(
          "getPlatformLink(userAgent: string, token?: string, route?: 'chat' | 'tasks')",
        ),
        'Should declare getPlatformLink',
      );
      assert.ok(
        content.includes('omi://h.omi.me/chat/${token}'),
        'Should have iOS chat redirect',
      );
      assert.ok(
        content.includes(
          'intent://h.omi.me/chat/${token}#Intent;scheme=https;package=com.friend.ios;S.browser_fallback_url=',
        ),
        'Should have Android chat redirect',
      );
      assert.ok(
        content.includes('return PRODUCT_CONFIG.storeUrl;'),
        'Should fall back to storeUrl',
      );
    });
  });

  describe('web/frontend/src/app/page.tsx', () => {
    it('redirects to /apps and does not contain legacy domain', () => {
      const content = readFile('web/frontend/src/app/page.tsx');
      assert.ok(
        content.includes("redirect('/apps')"),
        'Should redirect to /apps',
      );
      assert.ok(
        !content.includes('basedhardware.com/'),
        'Should not contain legacy domain',
      );
    });
  });

  describe('web/frontend/src/app/components/product-banner/types.ts', () => {
    it('updates PRODUCT_INFO dynamically from PRODUCT_CONFIG', () => {
      const content = readFile('web/frontend/src/app/components/product-banner/types.ts');
      assert.ok(
        content.includes('name: PRODUCT_CONFIG.name'),
        'Name should be derived from config',
      );
      assert.ok(
        content.includes('price: `$${PRODUCT_CONFIG.price}`'),
        'Price should be derived from config',
      );
      assert.ok(
        content.includes('url: `${PRODUCT_CONFIG.productUrl}'),
        'URL should be derived from config',
      );
    });
  });

  describe('web/frontend/src/app/apps/utils/metadata.ts', () => {
    it('references PRODUCT_CONFIG for productInfo and appStoreInfo', () => {
      const content = readFile('web/frontend/src/app/apps/utils/metadata.ts');
      assert.ok(
        content.includes('name: PRODUCT_CONFIG.name'),
        'Product name should pull from config',
      );
      assert.ok(
        content.includes('price: PRODUCT_CONFIG.price'),
        'Product price should pull from config',
      );
      assert.ok(
        content.includes('url: PRODUCT_CONFIG.productUrl'),
        'Product URL should pull from config',
      );
      assert.ok(
        content.includes('ios: PRODUCT_CONFIG.appStoreUrl'),
        'App Store iOS URL should pull from config',
      );
      assert.ok(
        content.includes('android: PRODUCT_CONFIG.playStoreUrl'),
        'Play Store Android URL should pull from config',
      );
    });

    it('replaces all "OMI Necklace" references with "Omi" in category metadata', () => {
      const content = readFile('web/frontend/src/app/apps/utils/metadata.ts');
      assert.ok(
        !content.includes('OMI Necklace'),
        'Should not contain OMI Necklace in metadata',
      );
    });
  });

  describe('web/frontend/src/app/apps/[id]/page.tsx', () => {
    it('references PRODUCT_CONFIG and delegates platform redirect logic', () => {
      const content = readFile('web/frontend/src/app/apps/[id]/page.tsx');
      assert.ok(
        content.includes('applicationSuite: PRODUCT_CONFIG.name'),
        'Suite name should pull from config',
      );
      assert.ok(
        content.includes('name: PRODUCT_CONFIG.name'),
        'Product name should pull from config',
      );
      assert.ok(
        content.includes('price: PRODUCT_CONFIG.price'),
        'Product price should pull from config',
      );
      assert.ok(
        content.includes('return PRODUCT_CONFIG.getPlatformLink(userAgent);'),
        'Platform redirect should delegate to config',
      );
    });
  });

  describe('web/frontend/src/app/apps/category/[category]/page.tsx', () => {
    it('removes hardcoded omi.me canonical URL and "OMI Necklace" text', () => {
      const content = readFile('web/frontend/src/app/apps/category/[category]/page.tsx');
      assert.ok(
        content.includes(
          'canonicalUrl = `${envConfig.WEB_URL}/apps/category/${category}`',
        ),
        'Canonical URL should use WEB_URL',
      );
      assert.ok(!content.includes('OMI Necklace'), 'Should not contain OMI Necklace');
    });
  });

  describe('web/frontend/src/app/apps/page.tsx', () => {
    it('replaces "OMI Necklace" in title and description metadata', () => {
      const content = readFile('web/frontend/src/app/apps/page.tsx');
      assert.ok(!content.includes('OMI Necklace'), 'Should not contain OMI Necklace');
      assert.ok(
        content.includes('Marketplace - AI-Powered Apps for Your Omi'),
        'Title should be updated',
      );
    });
  });

  describe('Shared page fallbacks (chat, tasks, recaps)', () => {
    it('updates chat fallback link logic to delegate to config', () => {
      const content = readFile('web/frontend/src/app/chat/[token]/page.tsx');
      assert.ok(
        content.includes(
          "return PRODUCT_CONFIG.getPlatformLink(userAgent, token, 'chat');",
        ),
        'Chat page fallback should delegate',
      );
    });

    it('updates tasks fallback link logic to delegate to config', () => {
      const content = readFile('web/frontend/src/app/tasks/[token]/page.tsx');
      assert.ok(
        content.includes(
          "return PRODUCT_CONFIG.getPlatformLink(userAgent, token, 'tasks');",
        ),
        'Tasks page fallback should delegate',
      );
    });

    it('updates recaps footer link to reference storeUrl', () => {
      const content = readFile('web/frontend/src/app/recaps/[id]/page.tsx');
      assert.ok(
        content.includes('href={PRODUCT_CONFIG.storeUrl}'),
        'Recaps page footer link should reference storeUrl',
      );
    });
  });

  describe('web/frontend/src/components/shared/app-header.tsx', () => {
    it('redirects brand logo link to www.omi.me', () => {
      const content = readFile('web/frontend/src/components/shared/app-header.tsx');
      assert.ok(
        content.includes('<a href="https://www.omi.me"'),
        'Brand logo should link to www.omi.me',
      );
    });
  });
});
