import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  ITEM_LINK_KINDS,
  ITEM_LINK_METADATA,
  isItemLinkId,
  itemLinkWebAppPath,
  itemLinkWebHandoff,
} from '../lib/item-link.mjs';
import { getOmiPlatformDeepLink } from '../lib/conversation-share-platform-link.mjs';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const fallbackSource = read('../components/item-link/item-link-fallback.tsx');
const pageSources = Object.fromEntries(
  ITEM_LINK_KINDS.map((kind) => [kind, read(`../app/${kind}/[id]/page.tsx`)]),
);
const aasa = JSON.parse(read('../../public/.well-known/apple-app-site-association'));

describe('private item links', () => {
  it('use singular kinds that never collide with the public share pages', () => {
    assert.deepEqual([...ITEM_LINK_KINDS], ['conversation', 'task', 'memory']);
  });

  it('accept opaque ids only', () => {
    assert.ok(isItemLinkId('a1B2-c3_d4'));
    assert.ok(!isItemLinkId(''));
    assert.ok(!isItemLinkId('../etc'));
    assert.ok(!isItemLinkId('a'.repeat(129)));
    assert.ok(!isItemLinkId('<script>'));
  });

  it('hand off to the signed-in web app through login', () => {
    assert.equal(itemLinkWebAppPath('conversation', 'c-1'), '/conversations?id=c-1');
    assert.equal(itemLinkWebAppPath('task', 't-1'), '/tasks');
    assert.equal(itemLinkWebAppPath('memory', 'm-1'), '/memories');
    assert.equal(
      itemLinkWebHandoff('conversation', 'c-1'),
      'https://app.omi.me/login?next=%2Fconversations%3Fid%3Dc-1',
    );
  });

  it('open the app through the same platform links as other h.omi.me pages', () => {
    assert.equal(
      getOmiPlatformDeepLink(
        'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)',
        'task/t-1',
      ),
      'omi://h.omi.me/task/t-1',
    );
    assert.match(
      getOmiPlatformDeepLink('Mozilla/5.0 (Linux; Android 14)', 'memory/m-1'),
      /^intent:\/\/h\.omi\.me\/memory\/m-1#Intent;scheme=https;package=com\.friend\.ios;/,
    );
  });

  it('give link previews generic Omi metadata only', () => {
    assert.deepEqual(ITEM_LINK_METADATA.title, { absolute: 'Omi' });
    assert.equal(ITEM_LINK_METADATA.openGraph.title, 'Omi');
    assert.deepEqual(ITEM_LINK_METADATA.robots, { index: false, follow: false });
    for (const [kind, source] of Object.entries(pageSources)) {
      assert.match(source, /export const metadata: Metadata = ITEM_LINK_METADATA/, kind);
      assert.doesNotMatch(
        source,
        /generateMetadata/,
        `${kind} must not build per-item metadata`,
      );
    }
  });

  it('never read the item: no backend fetch anywhere on the fallback', () => {
    for (const source of [fallbackSource, ...Object.values(pageSources)]) {
      assert.doesNotMatch(source, /\bfetch\(|API_URL|sharedApiUrl|actions\//);
    }
  });

  it('never echoes the id as HTML', () => {
    assert.doesNotMatch(fallbackSource, /dangerouslySetInnerHTML|innerHTML|>\s*\{id\}/);
    for (const source of Object.values(pageSources)) {
      assert.doesNotMatch(source, /dangerouslySetInnerHTML|>\s*\{id\}/);
    }
  });

  it('are universal links for the app, alongside the existing paths', () => {
    const paths = aasa.applinks.details[0].components.map((c) => c['/']);
    for (const kind of ITEM_LINK_KINDS) assert.ok(paths.includes(`/${kind}/*`), kind);
    for (const existing of ['/apps/*', '/unlimited', '/wrapped', '/tasks/*']) {
      assert.ok(paths.includes(existing), existing);
    }
    assert.ok(!paths.includes('/conversations/*'), 'public shares stay on the web');
  });
});
