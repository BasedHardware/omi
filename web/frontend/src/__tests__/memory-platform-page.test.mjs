import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

const frontendRoot = fileURLToPath(new URL('../', import.meta.url));
const read = (path) => readFile(new URL(path, `file://${frontendRoot}/`), 'utf8');

describe('memory platform website contract', () => {
  it('publishes the authority story and developer entry points', async () => {
    const page = await read('components/memory-platform/platform-page.tsx');

    assert.match(page, /Memory that can/);
    assert.match(page, /omi_backend/);
    assert.match(page, /zkr is the mirror/);
    assert.match(page, /\/memory-platform\/docs/);
    assert.match(page, /\/memory-platform\/embed/);
  });

  it('documents bounded API access and safe embedding', async () => {
    const docs = await read('app/memory-platform/docs/page.tsx');
    const embed = await read('app/memory-platform/embed/page.tsx');

    assert.match(docs, /v1\/memory\/platform\/search/);
    assert.match(docs, /v1\/memory\/platform\/ingest/);
    assert.match(docs, /query ≤ 500/);
    assert.match(embed, /server-side proxy/);
    assert.match(embed, /postMessage/);
    assert.match(embed, /sandbox/);
  });

  it('quotes the same search limit the backend router enforces', async () => {
    const readService = await readFile(
      new URL(
        '../../../../backend/utils/memory/product_memory_read_service.py',
        `file://${frontendRoot}/`,
      ),
      'utf8',
    );
    const backendLimit = /MAX_PRODUCT_MEMORY_READ_LIMIT = (\d+)/.exec(readService)?.[1];
    assert.ok(backendLimit, 'backend must define MAX_PRODUCT_MEMORY_READ_LIMIT');

    const docs = await read('app/memory-platform/docs/page.tsx');
    assert.match(docs, new RegExp(`limit 1–${backendLimit}\\b`));
  });

  it('never publishes an iframe sandbox the frame can remove', async () => {
    const sources = await Promise.all([
      read('app/memory-platform/embed/page.tsx'),
      read('components/memory-platform/platform-page.tsx'),
      readFile(
        new URL('../../../../docs/memory/embedding.md', `file://${frontendRoot}/`),
        'utf8',
      ),
    ]);

    for (const source of sources) {
      for (const [, tokens] of source.matchAll(/sandbox="([^"]*)"/g)) {
        const values = tokens.split(/\s+/).filter(Boolean);
        assert.ok(
          !(values.includes('allow-scripts') && values.includes('allow-same-origin')),
          `sandbox="${tokens}" lets the framed document remove its own sandbox`,
        );
      }
    }
  });

  it('proxies through a server-owned token instead of the caller header', async () => {
    const embed = await read('app/memory-platform/embed/page.tsx');

    assert.match(embed, /getOmiTokenForTenant/);
    assert.doesNotMatch(embed, /request\.headers\.get\("Authorization"\)/);
  });
});
