/**
 * STATIC TRIPWIRES for the /memory-platform surface — not behavioral coverage.
 *
 * These tests read source text and assert on it. They do not render a component
 * or exercise a request. They exist because three contracts on this surface are
 * copied verbatim by readers or enforced elsewhere in the repo, and each has
 * drifted at least once: the documented `limit` bound, the iframe sandbox
 * pairing, and the rule that a raw API key never reaches browser storage.
 *
 * Run: cd web/frontend && npm test
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_SRC = path.resolve(HERE, '..');
const REPO_ROOT = path.resolve(FRONTEND_SRC, '..', '..', '..');
const SURFACE = path.join(FRONTEND_SRC, 'app', 'memory-platform');

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

const SURFACE_FILES = walk(SURFACE);
const SOURCE_FILES = SURFACE_FILES.filter((file) => /\.(tsx?|css)$/.test(file));
const read = (file) => readFileSync(file, 'utf8');

describe('memory-platform routes exist', () => {
  const ROUTES = [
    'page.tsx',
    'docs/page.tsx',
    'embed/page.tsx',
    'keys/page.tsx',
    'billing/page.tsx',
    'widget/page.tsx',
  ];

  for (const route of ROUTES) {
    it(`ships ${route}`, () => {
      const full = path.join(SURFACE, route);
      assert.ok(SURFACE_FILES.includes(full), `${route} is missing`);
      assert.match(
        read(full),
        /generateMetadata|export const metadata/,
        `${route} must declare metadata`,
      );
    });
  }

  it('documents the package (check_arch_guardrails.py)', () => {
    assert.ok(SURFACE_FILES.includes(path.join(SURFACE, 'ARCHITECTURE.md')));
  });
});

describe('INV-UI-1: no purple on the memory-platform surface', () => {
  const BANNED = [
    /purple-(?:primary|secondary|accent|\d{2,4})\b/i,
    /#(?:7C3AED|8B5CF6|A855F7|9333EA|6D28D9|AF52DE|D946EF|A78BFA|C4B5FD)\b/i,
    /--purple-/,
    /\bpurple\b/i,
  ];

  for (const file of SOURCE_FILES) {
    it(`${path.relative(SURFACE, file)} is purple-free`, () => {
      const body = read(file);
      for (const pattern of BANNED) {
        assert.ok(!pattern.test(body), `${file} matches ${pattern}`);
      }
    });
  }
});

describe('iframe sandbox cannot be removed by the framed document', () => {
  const targets = [
    ...SOURCE_FILES,
    path.join(REPO_ROOT, 'docs', 'memory', 'embedding.md'),
    path.join(REPO_ROOT, 'docs', 'memory', 'api-service.md'),
  ];

  for (const file of targets) {
    it(`${path.basename(file)} never pairs allow-scripts with allow-same-origin`, () => {
      const body = read(file);
      const matches = [...body.matchAll(/sandbox=["{]?["']?([a-z- ]*)["']?/g)];
      for (const [, tokens] of matches) {
        const values = (tokens ?? '').split(/\s+/);
        assert.ok(
          !(values.includes('allow-scripts') && values.includes('allow-same-origin')),
          `${file}: sandbox="${tokens}" lets the framed document remove its own sandbox`,
        );
      }
    });
  }
});

describe('the embeddable widget is the one framable route', () => {
  // STATIC CHECKER: reads next.config.mjs rather than issuing requests.
  // The app sent `X-Frame-Options: DENY` on every route, which made the
  // embeddable widget — the entire point of this product — impossible to frame
  // in dev and in production. X-Frame-Options cannot be relaxed per-route by a
  // later rule, so the catch-all must exclude the widget path.
  const config = readFileSync(path.join(FRONTEND_SRC, '..', 'next.config.mjs'), 'utf8');

  it('excludes the widget from the deny-all frame policy', () => {
    assert.match(
      config,
      /source: '\/\(\(\?!memory-platform\/widget\)\.\*\)'/,
      'the X-Frame-Options catch-all must exclude /memory-platform/widget',
    );
  });

  it('lets the widget be framed by a host page', () => {
    assert.match(config, /source: '\/memory-platform\/widget'/);
    assert.match(config, /frame-ancestors \*/);
  });

  it('still denies framing everywhere else', () => {
    assert.match(config, /'X-Frame-Options'/);
    assert.match(config, /value: 'DENY'/);
  });
});

describe('raw API keys never reach durable browser storage', () => {
  it('no localStorage / sessionStorage / cookie writes on the surface', () => {
    for (const file of SOURCE_FILES) {
      const body = read(file);
      assert.ok(!/localStorage/.test(body), `${file} touches localStorage`);
      assert.ok(!/sessionStorage/.test(body), `${file} touches sessionStorage`);
      assert.ok(!/document\.cookie/.test(body), `${file} writes document.cookie`);
    }
  });

  it('the keys manager states the one-time reveal', () => {
    const body = read(path.join(SURFACE, 'components', 'keys-manager.tsx'));
    assert.match(body, /You will not see this key again/i);
  });

  it('no NEXT_PUBLIC_ key material is referenced', () => {
    for (const file of SOURCE_FILES) {
      assert.ok(
        !/NEXT_PUBLIC_[A-Z_]*(KEY|SECRET|TOKEN)/.test(read(file)),
        `${file} references a public key env var`,
      );
    }
  });
});

describe('documented bounds match the backend', () => {
  const backendSource = readFileSync(
    path.join(REPO_ROOT, 'backend', 'utils', 'memory', 'product_memory_read_service.py'),
    'utf8',
  );
  const enforcedLimit = Number(
    /MAX_PRODUCT_MEMORY_READ_LIMIT = (\d+)/.exec(backendSource)?.[1],
  );

  it('backend defines the limit', () => {
    assert.ok(Number.isInteger(enforcedLimit) && enforcedLimit > 0);
  });

  it('the client limit constant equals the enforced limit', () => {
    const body = readFileSync(
      path.join(FRONTEND_SRC, 'lib', 'api', 'memory-platform.ts'),
      'utf8',
    );
    const clientLimit = Number(/maxLimit: (\d+)/.exec(body)?.[1]);
    assert.equal(clientLimit, enforcedLimit);
  });

  it('the published doc quotes the enforced limit', () => {
    const doc = readFileSync(
      path.join(REPO_ROOT, 'docs', 'memory', 'api-service.md'),
      'utf8',
    );
    assert.ok(doc.includes(`\`limit\` to ${enforcedLimit} results`));
  });
});

describe('backend seams are isolated to one client function each', () => {
  it('rotation lives only in src/lib/api/mcp-keys.ts', () => {
    const client = readFileSync(
      path.join(FRONTEND_SRC, 'lib', 'api', 'mcp-keys.ts'),
      'utf8',
    );
    assert.match(client, /\/rotate/);
    for (const file of SOURCE_FILES) {
      assert.ok(
        !/\/v1\/mcp\/keys/.test(read(file)),
        `${file} calls the keys API directly`,
      );
    }
  });

  it('platform quota lives only in src/lib/api/billing.ts', () => {
    const client = readFileSync(
      path.join(FRONTEND_SRC, 'lib', 'api', 'billing.ts'),
      'utf8',
    );
    assert.match(client, /\/v1\/memory\/platform\/quota/);
    for (const file of SOURCE_FILES) {
      const source = read(file);
      // Scan for the endpoint this seam actually protects, plus the payments
      // paths the panel also reads. Checking only /v1/payments/ let a direct
      // call to the quota route through undetected.
      assert.ok(
        !/v1\/memory\/platform\/quota/.test(source),
        `${file} calls the platform quota API directly`,
      );
      assert.ok(!/v1\/payments\//.test(source), `${file} calls the payments API directly`);
    }
  });
});
