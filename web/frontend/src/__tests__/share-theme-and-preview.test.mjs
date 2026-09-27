import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';
import vm from 'node:vm';

import {
  SHARE_THEME_ATTRIBUTE,
  SHARE_THEME_BOOT_SCRIPT,
  SHARE_THEME_STORAGE_KEY,
  effectiveShareTheme,
  isShareNotePath,
  normalizeShareTheme,
  toggledShareTheme,
} from '../lib/share-theme.mjs';
import { getOmiInstallLink } from '../lib/conversation-share-platform-link.mjs';
import { previewBullets } from '../lib/shared-note.mjs';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const fixture = JSON.parse(read('../__fixtures__/shared-note.sample.json'));
const cssSource = read('../app/memories/[id]/share-note.css');
const pageSource = read('../app/memories/[id]/page.tsx');
const ogSource = read('../app/memories/[id]/og/route.tsx');

function runBootScript(storage) {
  const attributes = {};
  const context = {
    localStorage: storage,
    document: {
      documentElement: {
        setAttribute: (name, value) => {
          attributes[name] = value;
        },
      },
    },
  };
  vm.runInNewContext(SHARE_THEME_BOOT_SCRIPT, context);
  return attributes;
}

describe('share page theme', () => {
  it('follows the system until the viewer picks a theme', () => {
    assert.equal(effectiveShareTheme(null, true), 'dark');
    assert.equal(effectiveShareTheme(null, false), 'light');
    assert.equal(effectiveShareTheme('light', true), 'light');
    assert.equal(effectiveShareTheme('dark', false), 'dark');
    assert.equal(effectiveShareTheme('purple', true), 'dark');
  });

  it('toggles between the two themes and rejects anything else', () => {
    assert.equal(toggledShareTheme('dark'), 'light');
    assert.equal(toggledShareTheme('light'), 'dark');
    assert.equal(normalizeShareTheme('sepia'), null);
  });

  it('applies a saved choice before paint and survives blocked storage', () => {
    const saved = runBootScript({ getItem: () => 'dark' });
    assert.deepEqual(saved, { [SHARE_THEME_ATTRIBUTE]: 'dark' });
    assert.deepEqual(runBootScript({ getItem: () => null }), {});
    assert.deepEqual(runBootScript({ getItem: () => 'neon' }), {});
    const blocked = {
      getItem: () => {
        throw new Error('SecurityError');
      },
    };
    assert.deepEqual(runBootScript(blocked), {});
    assert.match(SHARE_THEME_BOOT_SCRIPT, new RegExp(SHARE_THEME_STORAGE_KEY));
  });

  it('styles dark for the system preference and for an explicit choice only', () => {
    assert.match(
      cssSource,
      /prefers-color-scheme:\s*dark\)\s*\{\s*:root:not\(\[data-share-theme='light'\]\) \.share-note/,
    );
    assert.match(cssSource, /:root\[data-share-theme='dark'\] \.share-note \{/);
    assert.match(pageSource, /<ShareThemeBoot \/>/);
  });

  it('uses no purple on the share page (INV-UI-1)', () => {
    assert.doesNotMatch(cssSource, /purple|violet|#[0-9a-f]*(8b5cf6|7c3aed|9333ea)/i);
  });
});

describe('share routes', () => {
  it('matches only individual shared notes', () => {
    assert.ok(isShareNotePath('/conversations/abc-123'));
    assert.ok(isShareNotePath('/memories/abc-123'));
    assert.ok(!isShareNotePath('/conversations'));
    assert.ok(!isShareNotePath('/apps/abc'));
    assert.ok(!isShareNotePath('/conversations/abc/og'));
    assert.ok(!isShareNotePath(null));
  });
});

describe('getOmiInstallLink', () => {
  it('sends phones to their store and everything else to omi.me', () => {
    assert.match(
      getOmiInstallLink('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)'),
      /^https:\/\/apps\.apple\.com\//,
    );
    assert.match(
      getOmiInstallLink('Mozilla/5.0 (Linux; Android 14)'),
      /^https:\/\/play\.google\.com\//,
    );
    assert.equal(getOmiInstallLink('Mozilla/5.0 (Macintosh)'), 'https://omi.me');
    assert.doesNotMatch(getOmiInstallLink('iPhone'), /^omi:/);
  });
});

describe('link preview image', () => {
  it('takes the first section bullets from a structured note', () => {
    assert.deepEqual(previewBullets(fixture.structured), [
      'Launch date confirmed for March 18.',
      'Pricing page copy approved with minor edits.',
      'Support macros need a refresh before launch.',
    ]);
  });

  it('falls back to overview bullets and skips nested ones', () => {
    assert.deepEqual(
      previewBullets({ overview: '## Heading\n\n- First\n  - nested\n- Second' }),
      ['First', 'Second'],
    );
    assert.deepEqual(previewBullets({}), []);
    assert.deepEqual(previewBullets(undefined), []);
  });

  it('is wired into the page metadata and never cached for a year', () => {
    assert.match(pageSource, /url: `\$\{ogUrl\}\/og`/);
    assert.match(pageSource, /twitter:/);
    assert.match(ogSource, /ImageResponse/);
    assert.match(ogSource, /'Cache-Control'/);
    assert.doesNotMatch(ogSource, /max-age=31536000/);
  });
});
