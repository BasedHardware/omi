import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildLegacyReport,
  assertNotNewStack,
  assertServedTraffic,
  finalizeLegacyReport,
} from './report.mjs';

const SAMPLE_BASE = 'http://127.0.0.1:51234';

describe('buildLegacyReport', () => {
  // red-proof: omit generation:'legacy' from the top-level report object
  it('stamps generation:legacy on the report and every domain row', () => {
    const report = buildLegacyReport({
      baseUrl: SAMPLE_BASE,
      domains: [{ name: 'tasks', ok: true, servedRequests: 2 }],
    });

    assert.equal(report.generation, 'legacy');
    assert.equal(report.baseUrl, SAMPLE_BASE);
    assert.equal(report.domains[0].generation, 'legacy');
    assertNotNewStack(report);
  });
});

describe('assertNotNewStack', () => {
  // red-proof: allow generation:'new' through assertNotNewStack without throwing
  it('throws when a caller labels the report as new-stack', () => {
    assert.throws(
      () => assertNotNewStack({ generation: 'new', baseUrl: SAMPLE_BASE, domains: [] }),
      /refusing to treat generation:new/,
    );
  });

  // red-proof: stop stamping generation on individual domain rows inside buildLegacyReport
  it('throws when a domain row is missing generation:legacy', () => {
    assert.throws(
      () =>
        assertNotNewStack({
          generation: 'legacy',
          baseUrl: SAMPLE_BASE,
          domains: [{ name: 'tasks', ok: true, servedRequests: 1 }],
        }),
      /not stamped generation:legacy/,
    );
  });
});

describe('assertServedTraffic', () => {
  // red-proof: delete the servedRequests===0 guard inside assertServedTraffic
  it('rejects ok:true domains that served zero requests', () => {
    const report = buildLegacyReport({
      baseUrl: SAMPLE_BASE,
      domains: [
        { name: 'tasks', ok: true, servedRequests: 0 },
        { name: 'conversations', ok: true, servedRequests: 2 },
        { name: 'folders', ok: true, servedRequests: 1 },
      ],
    });

    assert.throws(() => assertServedTraffic(report), /servedRequests:0/);
  });

  // red-proof: treat totalServed===0 as acceptable when every domain has ok:false
  it('rejects reports with zero total served traffic', () => {
    const report = buildLegacyReport({
      baseUrl: SAMPLE_BASE,
      domains: [
        { name: 'tasks', ok: false, servedRequests: 0, failure: 'down' },
        { name: 'conversations', ok: false, servedRequests: 0, failure: 'down' },
      ],
    });

    assert.throws(() => assertServedTraffic(report), /served zero domain requests/);
  });
});

describe('finalizeLegacyReport', () => {
  // red-proof: return the report without checking domain.ok in finalizeLegacyReport
  it('requires every domain to be ok after traffic validation', () => {
    const report = buildLegacyReport({
      baseUrl: SAMPLE_BASE,
      domains: [
        { name: 'tasks', ok: false, servedRequests: 1, failure: 'shape mismatch' },
        { name: 'conversations', ok: true, servedRequests: 1 },
      ],
    });

    assert.throws(() => finalizeLegacyReport(report), /legacy domains failed/);
  });
});
