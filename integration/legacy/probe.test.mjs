import { describe, it, after } from 'node:test';
import assert from 'node:assert/strict';
import { bootLegacyServer } from './boot.mjs';
import { probeLegacyDomains, assertActionItemsShape } from './probe.mjs';
import { buildLegacyReport, finalizeLegacyReport } from './report.mjs';

describe('probeLegacyDomains', () => {
  /** @type {Array<() => Promise<void>>} */
  const cleanups = [];

  after(async () => {
    await Promise.all(cleanups.map((stop) => stop()));
  });

  // red-proof: skip assertActionItemsShape() so malformed payloads pass
  it('returns consumable legacy shapes with nonzero served traffic per domain', async () => {
    const server = await bootLegacyServer();
    cleanups.push(server.stop);

    const domains = await probeLegacyDomains({ baseUrl: server.baseUrl });
    const report = buildLegacyReport({ baseUrl: server.baseUrl, domains });

    assert.equal(report.generation, 'legacy');
    assert.equal(report.baseUrl, server.baseUrl);
    assert.deepEqual(
      report.domains.map((row) => row.name),
      ['tasks', 'conversations', 'folders'],
    );

    for (const domain of report.domains) {
      assert.equal(domain.generation, 'legacy');
      assert.equal(domain.ok, true, domain.failure);
      assert.ok(domain.servedRequests > 0, `${domain.name} must have served real requests`);
    }

    finalizeLegacyReport(report);
  });

  // red-proof: point probe at a port with no server so fetch throws before any hitCount delta
  it('marks failed domains with a failure reason instead of silent ok', async () => {
    const domains = await probeLegacyDomains({ baseUrl: 'http://127.0.0.1:1' });
    assert.ok(domains.length >= 1);
    assert.equal(domains[0].ok, false);
    assert.ok(domains[0].failure);
  });
});

describe('probe shape guards', () => {
  // red-proof: accept an empty action_items array in assertActionItemsShape()
  it('rejects action-items payloads missing list rows', () => {
    assert.throws(() => assertActionItemsShape({ action_items: [] }), /non-empty action_items/);
  });
});
