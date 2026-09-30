import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  MIN_REFRESH_INTERVAL_MS,
  URL_REFRESH_MARGIN_MS,
  captureOffsetLabel,
  createRefreshGate,
  earliestExpiryMs,
  fitSize,
  groundGradient,
  msUntilRefresh,
  nextFrameSet,
  screenshotTiles,
  stepIndex,
} from '../lib/shared-screenshots.mjs';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const componentSource = read('../components/memories/summary/screen-moments.tsx');
const actionSource = read('../actions/memories/get-shared-screenshots.ts');
const pageSource = read('../app/memories/[id]/page.tsx');
const summarySource = read('../components/memories/summary/sumary.tsx');
const cssSource = read('../app/memories/[id]/share-note.css');

function frame(id, overrides = {}) {
  return {
    id,
    captured_at: '2026-09-30T01:50:09Z',
    role: 'strip',
    rank: 0,
    caption: `caption ${id}`,
    labels: [],
    source_badge: null,
    width: 1494,
    height: 1072,
    content_url: `https://storage.googleapis.com/b/${id}.jpg?sig=1`,
    thumbnail_url: `https://storage.googleapis.com/b/${id}-thumb.jpg?sig=1`,
    url_expires_at: '2026-09-30T03:47:39Z',
    ground: { stops: ['#447075', '#203547'], is_neutral: false },
    ...overrides,
  };
}

describe('screenshotTiles', () => {
  it('is empty for a missing, empty, or malformed set', () => {
    assert.deepEqual(screenshotTiles(null), []);
    assert.deepEqual(screenshotTiles(undefined), []);
    assert.deepEqual(screenshotTiles({ revision: 0, banner: null, strip: [] }), []);
    assert.deepEqual(screenshotTiles({ revision: 0 }), []);
    assert.deepEqual(screenshotTiles('nope'), []);
  });

  it('puts the banner first, then the strip in rank order', () => {
    const set = {
      revision: 1,
      banner: frame('b', { role: 'banner' }),
      strip: [
        frame('s2', { rank: 2 }),
        frame('s0', { rank: 0 }),
        frame('s1', { rank: 1 }),
      ],
    };
    assert.deepEqual(
      screenshotTiles(set).map((f) => f.id),
      ['b', 's0', 's1', 's2'],
    );
  });

  it('shows a frame once when the banner is also in the strip', () => {
    const set = {
      revision: 1,
      banner: frame('x'),
      strip: [frame('x'), frame('y', { rank: 1 })],
    };
    assert.deepEqual(
      screenshotTiles(set).map((f) => f.id),
      ['x', 'y'],
    );
  });

  it('drops entries without urls, dimensions, or a parseable expiry', () => {
    const set = {
      revision: 1,
      strip: [
        frame('ok'),
        frame('no-url', { content_url: undefined }),
        frame('no-size', { width: 0 }),
        frame('no-expiry', { url_expires_at: 'soon' }),
      ],
    };
    assert.deepEqual(
      screenshotTiles(set).map((f) => f.id),
      ['ok'],
    );
  });
});

describe('signed-url refresh timing', () => {
  const tiles = [
    frame('a', { url_expires_at: '2026-09-30T03:00:00Z' }),
    frame('b', { url_expires_at: '2026-09-30T02:30:00Z' }),
  ];

  it('finds the earliest expiry', () => {
    assert.equal(earliestExpiryMs(tiles), Date.parse('2026-09-30T02:30:00Z'));
    assert.equal(earliestExpiryMs([]), null);
  });

  it('refetches a margin before the earliest url expires', () => {
    const now = Date.parse('2026-09-30T02:00:00Z');
    assert.equal(msUntilRefresh(tiles, now), 30 * 60 * 1000 - URL_REFRESH_MARGIN_MS);
  });

  it('is due immediately once inside the margin or past expiry', () => {
    assert.equal(msUntilRefresh(tiles, Date.parse('2026-09-30T02:29:00Z')), 0);
    assert.equal(msUntilRefresh(tiles, Date.parse('2026-09-30T05:00:00Z')), 0);
    assert.equal(msUntilRefresh([], 0), 0);
  });

  it('keeps a floor between refetches so a fast clock cannot loop', () => {
    assert.ok(MIN_REFRESH_INTERVAL_MS >= 10_000);
    // The floor lives in createRefreshGate (tested below); the component must route through it.
    assert.match(componentSource, /createRefreshGate\(/);
    assert.doesNotMatch(componentSource, /lastRefreshAt/);
  });
});

describe('lightbox helpers', () => {
  it('steps with wraparound', () => {
    assert.equal(stepIndex(0, 7, -1), 6);
    assert.equal(stepIndex(6, 7, 1), 0);
    assert.equal(stepIndex(3, 7, 1), 4);
    assert.equal(stepIndex(0, 0, 1), 0);
  });

  it('fits to the viewport without upscaling, keeping the aspect ratio', () => {
    assert.deepEqual(fitSize(1494, 1072, 2000, 2000), {
      width: 1494,
      height: 1072,
      scale: 1,
    });
    const fit = fitSize(1494, 1072, 800, 1000);
    assert.equal(fit.width, 800);
    assert.equal(fit.height, Math.round(1072 * (800 / 1494)));
    const tall = fitSize(1494, 1072, 2000, 500);
    assert.equal(tall.height, 500);
    assert.deepEqual(fitSize(0, 10, 10, 10), { width: 0, height: 0, scale: 0 });
  });

  it('labels the capture offset from the call start', () => {
    assert.equal(
      captureOffsetLabel('2026-09-30T01:50:09Z', '2026-09-30T01:45:09Z'),
      '5:00',
    );
    assert.equal(
      captureOffsetLabel('2026-09-30T03:02:03Z', '2026-09-30T01:45:09Z'),
      '1:16:54',
    );
    assert.equal(captureOffsetLabel('2026-09-30T01:40:00Z', '2026-09-30T01:45:09Z'), '');
    assert.equal(captureOffsetLabel('2026-09-30T01:50:09Z', null), '');
  });

  it('builds the loading gradient only from valid hex stops', () => {
    assert.equal(groundGradient(frame('a')), 'linear-gradient(135deg, #447075, #203547)');
    assert.equal(
      groundGradient(frame('a', { ground: { stops: ['red', 'url(x)'] } })),
      undefined,
    );
    assert.equal(groundGradient({}), undefined);
  });
});

describe('share page wiring', () => {
  it('fetches the public route per request, never cached', () => {
    assert.match(actionSource, /'shared',\s*'screenshots'/);
    assert.match(actionSource, /cache: 'no-store'/);
    assert.doesNotMatch(actionSource, /revalidate/);
    assert.match(pageSource, /getSharedScreenshots\(memoryId\)/);
  });

  it('renders the strip in the Notes tab after action items', () => {
    const actions = summarySource.indexOf('<ActionItems');
    const moments = summarySource.indexOf('<ScreenMoments');
    assert.ok(actions > 0 && moments > actions);
  });

  it('hides the strip entirely when there is nothing to show', () => {
    assert.match(componentSource, /if \(tiles\.length === 0\) return null;/);
  });

  it('uses an accessible dialog with arrows, Esc, and a focus trap', () => {
    assert.match(componentSource, /@radix-ui\/react-dialog/);
    assert.match(componentSource, /Dialog\.Title/);
    assert.match(componentSource, /ArrowLeft/);
    assert.match(componentSource, /ArrowRight/);
    assert.match(componentSource, /onCloseAutoFocus/);
  });

  it('lazy-loads thumbnails with explicit dimensions', () => {
    assert.match(componentSource, /loading="lazy"/);
    assert.match(componentSource, /width=\{frame\.width\}/);
    assert.match(componentSource, /height=\{frame\.height\}/);
  });

  it('styles the strip with the share tokens', () => {
    assert.match(cssSource, /\.sn-shot-button\s*\{[^}]*var\(--sn-hairline\)/);
    assert.match(cssSource, /\.sn-lightbox\s*\{/);
  });
});

describe('createRefreshGate', () => {
  function harness() {
    let clock = 0;
    const timers = [];
    const runs = [];
    let release = () => {};
    const gate = createRefreshGate({
      run: () => {
        runs.push(clock);
        return new Promise((resolve) => {
          release = resolve;
        });
      },
      minIntervalMs: 30_000,
      now: () => clock,
      setTimer: (fn, ms) => {
        const t = { fn, at: clock + ms, cleared: false };
        timers.push(t);
        return t;
      },
      clearTimer: (t) => {
        if (t) t.cleared = true;
      },
    });
    const advance = async (ms) => {
      clock += ms;
      for (const t of timers) {
        if (!t.cleared && t.at <= clock) {
          t.cleared = true;
          t.fn();
        }
      }
      await Promise.resolve();
    };
    return {
      gate,
      runs,
      advance,
      finish: async () => {
        release();
        await new Promise((resolve) => setImmediate(resolve));
      },
    };
  }

  it('runs an unthrottled request immediately', async () => {
    const h = harness();
    h.gate.request();
    assert.deepEqual(h.runs, [0]);
  });

  it('defers a request made during the cooldown to its end instead of dropping it', async () => {
    const h = harness();
    await h.advance(60_000);
    h.gate.request();
    await h.finish();
    await h.advance(5_000); // an image error right after renewal
    h.gate.request();
    assert.deepEqual(h.runs, [60_000], 'must not run inside the cooldown');
    await h.advance(25_000);
    assert.deepEqual(h.runs, [60_000, 90_000], 'must run when the cooldown ends');
  });

  it('coalesces several cooldown requests into one deferred run', async () => {
    const h = harness();
    await h.advance(60_000);
    h.gate.request();
    await h.finish();
    h.gate.request();
    h.gate.request();
    await h.advance(30_000);
    assert.equal(h.runs.length, 2);
  });

  it('does not start a second run while one is in flight', async () => {
    const h = harness();
    await h.advance(60_000);
    h.gate.request();
    await h.advance(40_000);
    h.gate.request();
    assert.equal(h.runs.length, 1);
  });

  it('cancels a deferred run on dispose', async () => {
    const h = harness();
    await h.advance(60_000);
    h.gate.request();
    await h.finish();
    h.gate.request();
    h.gate.dispose();
    await h.advance(60_000);
    assert.equal(h.runs.length, 1);
  });
});

describe('transient refetch failures keep the set and retry', () => {
  function failingHarness(outcomes) {
    let clock = 0;
    const timers = [];
    const runs = [];
    const gate = createRefreshGate({
      run: () => {
        runs.push(clock);
        return outcomes.shift() === 'fail'
          ? Promise.reject(new Error('503'))
          : Promise.resolve();
      },
      minIntervalMs: 30_000,
      maxBackoffMs: 300_000,
      now: () => clock,
      setTimer: (fn, ms) => {
        const t = { fn, at: clock + ms, cleared: false };
        timers.push(t);
        return t;
      },
      clearTimer: (t) => {
        if (t) t.cleared = true;
      },
    });
    const settle = () => new Promise((resolve) => setImmediate(resolve));
    const advance = async (ms) => {
      clock += ms;
      for (const t of [...timers]) {
        if (!t.cleared && t.at <= clock) {
          t.cleared = true;
          t.fn();
        }
      }
      await settle();
    };
    return { gate, runs, advance, settle };
  }

  it('retries a failed refetch on its own, with growing, bounded backoff', async () => {
    const h = failingHarness(['fail', 'fail', 'ok']);
    await h.advance(1_000_000);
    h.gate.request();
    await h.settle();
    assert.equal(h.runs.length, 1);
    await h.advance(60_000); // first retry after 2 x base
    assert.equal(h.runs.length, 2);
    await h.advance(60_000); // second retry waits longer (4 x base)
    assert.equal(h.runs.length, 2);
    await h.advance(60_000);
    assert.equal(h.runs.length, 3);
    await h.advance(3_600_000); // success: no further unsolicited runs
    assert.equal(h.runs.length, 3);
  });

  it('caps the backoff', async () => {
    const h = failingHarness(Array(12).fill('fail'));
    await h.advance(1_000_000);
    h.gate.request();
    await h.settle();
    for (let i = 0; i < 10; i += 1) await h.advance(300_000);
    assert.equal(h.runs.length, 11);
  });

  it('keeps the last set on failure and clears only on a successful empty response', () => {
    const prev = { revision: 1, strip: [frame('a')] };
    assert.equal(nextFrameSet(prev, { ok: false }), prev);
    const empty = { revision: 2, banner: null, strip: [] };
    assert.equal(nextFrameSet(prev, { ok: true, set: empty }), empty);
    const renewed = { revision: 1, strip: [frame('a')] };
    assert.equal(nextFrameSet(prev, { ok: true, set: renewed }), renewed);
  });

  it('the server action distinguishes failure from an empty set', () => {
    assert.match(actionSource, /ok: false/);
    assert.match(actionSource, /ok: true/);
    assert.match(componentSource, /nextFrameSet\(/);
    assert.doesNotMatch(componentSource, /setFrameSet\(null\)/);
  });

  it('hides only the images that failed, not the strip', () => {
    assert.match(componentSource, /failedIds/);
    assert.match(cssSource, /\.sn-shot-failed/);
  });

  it('remounts images after a successful refetch even when the signed URL is unchanged', () => {
    // Measured live: after a failure the backend can return the identical
    // signed URL, and an <img> whose src does not change never retries.
    assert.match(componentSource, /if \(result\.ok\) setSetVersion\(/);
    assert.match(componentSource, /key=\{`\$\{frame\.id\}:\$\{setVersion\}`\}/);
    assert.match(componentSource, /key=\{`\$\{current\.id\}:\$\{setVersion\}`\}/);
  });

  it('remounts per conversation so state never carries across a client navigation', () => {
    assert.match(summarySource, /<ScreenMoments\s+key=\{memory\.id\}/);
  });
});
