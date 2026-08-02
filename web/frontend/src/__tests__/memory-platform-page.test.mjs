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
});
