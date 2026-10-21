import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const appsDir = path.join(frontendRoot, 'app/apps');
const productBannerDir = path.join(frontendRoot, 'app/components/product-banner');
const constantsPath = path.join(
  frontendRoot,
  'constants/app-store-hardware-product.ts',
);

const FORBIDDEN_PATTERNS = [
  /duo dev kit/i,
  /69\.99/,
  /\$69(?:\.99)?(?!\d)/,
  /products\/omi-dev-kit-2/i,
  /products\/friend-dev-kit-2/i,
];

function stripLineComments(source) {
  return source
    .split('\n')
    .map((line) => line.replace(/(?<!:)\/\/.*$/, ''))
    .join('\n');
}

function collectSourceFiles(dir) {
  const files = [];
  for (const entry of readdirSync(dir)) {
    const fullPath = path.join(dir, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      files.push(...collectSourceFiles(fullPath));
    } else if (/\.(tsx?|jsx?)$/.test(entry)) {
      files.push(fullPath);
    }
  }
  return files;
}

describe('app-store hardware product (Fixes #5855 guard)', () => {
  it('defines current Omi branding and $89 storefront URLs', () => {
    const source = readFileSync(constantsPath, 'utf8');
    assert.match(source, /name:\s*'Omi'/);
    assert.match(source, /displayPrice:\s*'\$89'/);
    assert.match(source, /schemaPrice:\s*'89'/);
    assert.match(source, /storeUrl:\s*'https:\/\/www\.omi\.me\/'/);
    assert.doesNotMatch(source, /duo dev kit/i);
    assert.doesNotMatch(source, /69\.99/);
  });

  it('keeps marketplace CTAs wired through the shared constant', () => {
    const bannerTypes = readFileSync(
      path.join(productBannerDir, 'types.ts'),
      'utf8',
    );
    const metadata = readFileSync(
      path.join(frontendRoot, 'app/apps/utils/metadata.ts'),
      'utf8',
    );
    const appDetail = readFileSync(
      path.join(frontendRoot, 'app/apps/[id]/page.tsx'),
      'utf8',
    );

    for (const property of [
      'APP_STORE_HARDWARE_PRODUCT.name',
      'APP_STORE_HARDWARE_PRODUCT.displayPrice',
      'APP_STORE_HARDWARE_PRODUCT.marketplaceOrderUrl',
      'APP_STORE_HARDWARE_PRODUCT.shipping',
      'APP_STORE_HARDWARE_PRODUCT.images',
    ]) {
      assert.match(
        bannerTypes,
        new RegExp(property.replace('.', '\\.')),
        `product-banner/types.ts must reference ${property}`,
      );
    }

    for (const property of [
      'APP_STORE_HARDWARE_PRODUCT.name',
      'APP_STORE_HARDWARE_PRODUCT.description',
      'APP_STORE_HARDWARE_PRODUCT.schemaPrice',
      'APP_STORE_HARDWARE_PRODUCT.currency',
      'APP_STORE_HARDWARE_PRODUCT.storeUrl',
    ]) {
      assert.match(
        metadata,
        new RegExp(property.replace('.', '\\.')),
        `apps/utils/metadata.ts must reference ${property}`,
      );
    }

    for (const property of [
      'APP_STORE_HARDWARE_PRODUCT.name',
      'APP_STORE_HARDWARE_PRODUCT.description',
      'APP_STORE_HARDWARE_PRODUCT.schemaPrice',
      'APP_STORE_HARDWARE_PRODUCT.currency',
    ]) {
      assert.match(
        appDetail,
        new RegExp(property.replace('.', '\\.')),
        `apps/[id]/page.tsx must reference ${property}`,
      );
    }
  });

  it('does not reintroduce discontinued Duo Dev Kit pricing or product slugs on app-store surfaces', () => {
    const surfaces = [
      constantsPath,
      ...collectSourceFiles(appsDir),
      ...collectSourceFiles(productBannerDir),
    ];

    for (const filePath of surfaces) {
      const withoutComments = stripLineComments(readFileSync(filePath, 'utf8'));
      for (const pattern of FORBIDDEN_PATTERNS) {
        assert.doesNotMatch(
          withoutComments,
          pattern,
          `${path.relative(frontendRoot, filePath)} must not match ${pattern}`,
        );
      }
    }
  });
});
