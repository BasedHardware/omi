import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

// Helper to read file content relative to project root
function readFile(relativePath) {
  let normalizedPath = relativePath;
  const normalizedCwd = process.cwd().replace(/\\/g, '/');
  if (normalizedCwd.endsWith('web/frontend') && relativePath.startsWith('web/frontend/')) {
    normalizedPath = relativePath.slice('web/frontend/'.length);
  }
  const filePath = path.join(process.cwd(), normalizedPath);
  return fs.readFileSync(filePath, 'utf8');
}

describe('Omi Store & Link Cleanup Validation', () => {
  describe('web/frontend/src/app/page.tsx', () => {
    it('redirects "Order now" link to www.omi.me instead of basedhardware.com', () => {
      const content = readFile('web/frontend/src/app/page.tsx');
      assert.ok(
        content.includes('href="https://www.omi.me/"'),
        'Should link to www.omi.me',
      );
      assert.ok(
        !content.includes('basedhardware.com/'),
        'Should not link to legacy basedhardware.com',
      );
    });
  });

  describe('web/frontend/src/app/components/product-banner/types.ts', () => {
    it('updates PRODUCT_INFO to name: "Omi" and price: "$89"', () => {
      const content = readFile('web/frontend/src/app/components/product-banner/types.ts');
      assert.ok(content.includes("name: 'Omi'"), 'Name should be Omi');
      assert.ok(content.includes("price: '$89'"), 'Price should be $89');
      assert.ok(!content.includes('OMI Necklace'), 'Should not use legacy OMI Necklace');
      assert.ok(!content.includes('69.99'), 'Should not use legacy price 69.99');
    });
  });

  describe('web/frontend/src/app/apps/utils/metadata.ts', () => {
    it('updates productInfo metadata', () => {
      const content = readFile('web/frontend/src/app/apps/utils/metadata.ts');
      assert.ok(content.includes("name: 'Omi'"), 'Product name should be Omi');
      assert.ok(content.includes("price: '89'"), 'Product price should be 89');
      assert.ok(
        content.includes("url: 'https://www.omi.me/products/omi-dev-kit-2'"),
        'Product URL should use omi-dev-kit-2',
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
    it('updates structured data name, price, productUrl and fallback link', () => {
      const content = readFile('web/frontend/src/app/apps/[id]/page.tsx');
      assert.ok(content.includes("name: 'Omi'"), 'Schema name should be Omi');
      assert.ok(content.includes("price: '89'"), 'Schema price should be 89');
      assert.ok(
        content.includes('omi-dev-kit-2?ref='),
        'Product schema URL should use omi-dev-kit-2',
      );
      assert.ok(
        content.includes("'https://www.omi.me'"),
        'Platform fallback on desktop should point to www.omi.me',
      );
      assert.ok(
        !content.includes('friend-dev-kit-2'),
        'Should not link to friend-dev-kit-2',
      );
      assert.ok(!content.includes('OMI Necklace'), 'Should not use OMI Necklace in page');
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
    it('updates chat fallback link to www.omi.me', () => {
      const content = readFile('web/frontend/src/app/chat/[token]/page.tsx');
      assert.ok(
        content.includes(": 'https://www.omi.me'"),
        'Chat page fallback should be www.omi.me',
      );
    });

    it('updates tasks fallback link to www.omi.me', () => {
      const content = readFile('web/frontend/src/app/tasks/[token]/page.tsx');
      assert.ok(
        content.includes(": 'https://www.omi.me'"),
        'Tasks page fallback should be www.omi.me',
      );
    });

    it('updates recaps footer link to www.omi.me', () => {
      const content = readFile('web/frontend/src/app/recaps/[id]/page.tsx');
      assert.ok(
        content.includes('href="https://www.omi.me"'),
        'Recaps page footer link should be www.omi.me',
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
