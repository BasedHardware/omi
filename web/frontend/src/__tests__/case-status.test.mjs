/**
 * Tests for case status page logic.
 * Run: node --test web/frontend/src/app/case/\[ref\]/case-status.test.mjs
 *
 * Uses Node.js built-in test runner (node:test) — no additional deps needed.
 * Tests pure functions and fetch behavior extracted from page.tsx.
 */
import { describe, it, mock, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

// ── Pure logic copied from page.tsx (same implementation) ──────────────

const SUPPORT_EMAIL = 'team@basedhardware.com';
const EMAIL_RE = /^[a-zA-Z0-9.!#$&'*+/=^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$/;

function safeEmail(raw) {
  return raw && EMAIL_RE.test(raw) ? raw : SUPPORT_EMAIL;
}

function formatDate(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function daysSince(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 0;
  return Math.floor((Date.now() - d.getTime()) / (1000 * 60 * 60 * 24));
}

const REF_RE = /^FU-[A-Fa-f0-9]{6,12}$/i;

const STAGE_META = {
  none: { label: 'Normal', dot: 'bg-green-400', text: 'text-green-400', bg: 'bg-green-500/[0.06]' },
  warning: { label: 'Warning', dot: 'bg-amber-400', text: 'text-amber-400', bg: 'bg-amber-500/[0.06]' },
  throttle: { label: 'Throttled', dot: 'bg-orange-400', text: 'text-orange-400', bg: 'bg-orange-500/[0.06]' },
  restrict: { label: 'Restricted', dot: 'bg-red-400', text: 'text-red-400', bg: 'bg-red-500/[0.06]' },
};

async function getCaseStatus(ref, fetchFn = globalThis.fetch) {
  try {
    const res = await fetchFn(`https://api.omi.me/v1/fair-use/case/${encodeURIComponent(ref)}/status`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(10_000),
    });
    if (res.status === 404) return { kind: 'not_found' };
    if (!res.ok) return { kind: 'error' };
    return { kind: 'ok', data: await res.json() };
  } catch {
    return { kind: 'error' };
  }
}

// ── Tests ──────────────────────────────────────────────────────────────

describe('ref format validation', () => {
  it('accepts valid 6-char hex ref', () => {
    assert.ok(REF_RE.test('FU-A1B2C3'));
  });
  it('accepts valid 12-char hex ref', () => {
    assert.ok(REF_RE.test('FU-A1B2C3D4E5F6'));
  });
  it('is case-insensitive', () => {
    assert.ok(REF_RE.test('FU-abcdef'));
    assert.ok(REF_RE.test('fu-ABCDEF'));
  });
  it('rejects too-short hex (5 chars)', () => {
    assert.ok(!REF_RE.test('FU-A1B2C'));
  });
  it('rejects too-long hex (13 chars)', () => {
    assert.ok(!REF_RE.test('FU-A1B2C3D4E5F6A'));
  });
  it('rejects non-hex chars', () => {
    assert.ok(!REF_RE.test('FU-GHIJKL'));
  });
  it('rejects missing prefix', () => {
    assert.ok(!REF_RE.test('A1B2C3'));
  });
  it('rejects empty string', () => {
    assert.ok(!REF_RE.test(''));
  });
  it('rejects path traversal attempt', () => {
    assert.ok(!REF_RE.test('FU-A1B2C3/../'));
  });
});

describe('safeEmail', () => {
  it('passes through valid email', () => {
    assert.equal(safeEmail('support@example.com'), 'support@example.com');
  });
  it('falls back for undefined', () => {
    assert.equal(safeEmail(undefined), SUPPORT_EMAIL);
  });
  it('falls back for empty string', () => {
    assert.equal(safeEmail(''), SUPPORT_EMAIL);
  });
  it('falls back for null', () => {
    assert.equal(safeEmail(null), SUPPORT_EMAIL);
  });
  it('rejects ? in email (mailto param injection)', () => {
    assert.equal(safeEmail('a?subject=x@example.com'), SUPPORT_EMAIL);
  });
  it('rejects % in email (URL encoding)', () => {
    assert.equal(safeEmail('a%40b@example.com'), SUPPORT_EMAIL);
  });
  it('rejects newline in email', () => {
    assert.equal(safeEmail('a\n@example.com'), SUPPORT_EMAIL);
  });
  it('rejects single-label domain', () => {
    assert.equal(safeEmail('user@localhost'), SUPPORT_EMAIL);
  });
  it('accepts subdomain emails', () => {
    assert.equal(safeEmail('user@sub.example.com'), 'user@sub.example.com');
  });
  it('accepts special RFC chars in local part', () => {
    assert.equal(safeEmail("user.name+tag@example.com"), "user.name+tag@example.com");
  });
});

describe('formatDate', () => {
  it('returns non-empty for valid ISO date', () => {
    const result = formatDate('2026-01-15T10:30:00Z');
    assert.ok(result.length > 0);
    assert.ok(result.includes('2026'));
    assert.ok(result.includes('Jan'));
  });
  it('returns empty string for invalid date', () => {
    assert.equal(formatDate('not-a-date'), '');
  });
  it('returns empty string for empty string', () => {
    assert.equal(formatDate(''), '');
  });
  it('handles epoch zero', () => {
    const result = formatDate('1970-01-01T00:00:00Z');
    assert.ok(result.includes('1970'));
  });
});

describe('daysSince', () => {
  it('returns 0 for invalid date', () => {
    assert.equal(daysSince('garbage'), 0);
  });
  it('returns 0 for today', () => {
    assert.equal(daysSince(new Date().toISOString()), 0);
  });
  it('returns correct days for past date', () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString();
    assert.equal(daysSince(threeDaysAgo), 3);
  });
  it('returns 0 for future date', () => {
    const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    // Future dates give negative floor, but function returns the floor value
    const result = daysSince(tomorrow);
    assert.ok(result <= 0);
  });
  it('boundary: exactly 3 days triggers stale banner', () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString();
    assert.ok(daysSince(threeDaysAgo) >= 3);
  });
  it('boundary: 2 days does not trigger stale banner', () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    assert.ok(daysSince(twoDaysAgo) < 3);
  });
});

describe('STAGE_META', () => {
  it('has all four stages', () => {
    for (const stage of ['none', 'warning', 'throttle', 'restrict']) {
      assert.ok(STAGE_META[stage], `missing stage: ${stage}`);
      assert.ok(STAGE_META[stage].label);
      assert.ok(STAGE_META[stage].dot);
      assert.ok(STAGE_META[stage].text);
      assert.ok(STAGE_META[stage].bg);
    }
  });
  it('unknown stage falls back to none via nullish coalescing', () => {
    const meta = STAGE_META['unknown'] ?? STAGE_META['none'];
    assert.equal(meta.label, 'Normal');
  });
});

describe('getCaseStatus', () => {
  it('returns ok for 200 response', async () => {
    const mockData = { case_ref: 'FU-ABC123', stage: 'none', message: '', created_at: '', updated_at: '' };
    const fakeFetch = mock.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => mockData,
    }));
    const result = await getCaseStatus('FU-ABC123', fakeFetch);
    assert.deepEqual(result, { kind: 'ok', data: mockData });
    assert.equal(fakeFetch.mock.calls.length, 1);
    assert.ok(fakeFetch.mock.calls[0].arguments[0].includes('FU-ABC123'));
  });

  it('returns not_found for 404', async () => {
    const fakeFetch = mock.fn(async () => ({ ok: false, status: 404 }));
    const result = await getCaseStatus('FU-ABC123', fakeFetch);
    assert.deepEqual(result, { kind: 'not_found' });
  });

  it('returns error for 500', async () => {
    const fakeFetch = mock.fn(async () => ({ ok: false, status: 500 }));
    const result = await getCaseStatus('FU-ABC123', fakeFetch);
    assert.deepEqual(result, { kind: 'error' });
  });

  it('returns error for network failure', async () => {
    const fakeFetch = mock.fn(async () => { throw new Error('network down'); });
    const result = await getCaseStatus('FU-ABC123', fakeFetch);
    assert.deepEqual(result, { kind: 'error' });
  });

  it('returns error for timeout (AbortError)', async () => {
    const fakeFetch = mock.fn(async () => { throw new DOMException('Aborted', 'AbortError'); });
    const result = await getCaseStatus('FU-ABC123', fakeFetch);
    assert.deepEqual(result, { kind: 'error' });
  });

  it('URL-encodes the ref parameter', async () => {
    const fakeFetch = mock.fn(async () => ({ ok: false, status: 404 }));
    await getCaseStatus('FU-AB CD12', fakeFetch);
    assert.ok(fakeFetch.mock.calls[0].arguments[0].includes('FU-AB%20CD12'));
  });

  it('passes signal option to fetch', async () => {
    const fakeFetch = mock.fn(async (_url, opts) => {
      assert.ok(opts.signal, 'signal should be present');
      return { ok: false, status: 404 };
    });
    await getCaseStatus('FU-ABC123', fakeFetch);
  });
});
