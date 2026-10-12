import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

import {
  ITEM_LINK_KINDS,
  ITEM_LINK_METADATA,
  ITEM_LIST_MAX,
  ITEM_LIST_QUERY_HEADER,
  MAC_APP_URL_SCHEME,
  isItemLinkId,
  isMacDesktopUserAgent,
  itemLinkWebAppPath,
  itemLinkWebHandoff,
  itemListFromSearchParams,
  itemListMacDeepLink,
  itemListMetadata,
  itemListWebAppPath,
  itemListWebHandoff,
  parseItemListQuery,
} from '../lib/item-link.mjs';
import { getOmiPlatformDeepLink } from '../lib/conversation-share-platform-link.mjs';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const fallbackSource = read('../components/item-link/item-link-fallback.tsx');
const pageSources = Object.fromEntries(
  ITEM_LINK_KINDS.map((kind) => [kind, read(`../app/${kind}/[id]/page.tsx`)]),
);
const itemListPage = read('../app/items/page.tsx');
const macButton = read('../components/item-link/mac-open-button.tsx');
const proxySource = read('../proxy.ts');
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

describe('private item lists (/items)', () => {
  it('keep URL order across kinds and drop unknown keys, bad ids and repeats', () => {
    assert.deepEqual(
      parseItemListQuery(
        '?task=t-1&utm_source=x&conversation=c-1&memory=m-1&task=t-1&memory=../x&conversation=',
      ),
      [
        { kind: 'task', id: 't-1' },
        { kind: 'conversation', id: 'c-1' },
        { kind: 'memory', id: 'm-1' },
      ],
    );
    assert.deepEqual(parseItemListQuery('%zz=1&memory=%E0'), []);
  });

  it('stop at ten items', () => {
    const query = Array.from({ length: 12 }, (_, i) => `task=t-${i}`).join('&');
    const items = parseItemListQuery(query);
    assert.equal(ITEM_LIST_MAX, 10);
    assert.equal(items.length, 10);
    assert.equal(items.at(-1).id, 't-9');
  });

  it('fall back to a parsed searchParams object when the raw query is missing', () => {
    assert.deepEqual(
      itemListFromSearchParams({ conversation: ['c-1', 'c-2'], task: 't-1', x: 'y' }),
      [
        { kind: 'conversation', id: 'c-1' },
        { kind: 'conversation', id: 'c-2' },
        { kind: 'task', id: 't-1' },
      ],
    );
  });

  it('hand off to the web app /items page through login', () => {
    const items = parseItemListQuery('memory=m-1&conversation=c-1');
    assert.equal(itemListWebAppPath(items), '/items?memory=m-1&conversation=c-1');
    assert.equal(itemListWebAppPath([]), '/home');
    assert.equal(
      itemListWebHandoff(items),
      'https://app.omi.me/login?next=%2Fitems%3Fmemory%3Dm-1%26conversation%3Dc-1',
    );
  });

  it('open the phone app and the released Mac app with the same ordered query', () => {
    const items = parseItemListQuery('task=t-1&conversation=c-1');
    assert.equal(MAC_APP_URL_SCHEME, 'omi-computer');
    assert.equal(
      itemListMacDeepLink(items),
      'omi-computer://items?task=t-1&conversation=c-1',
    );
    assert.equal(
      getOmiPlatformDeepLink(
        'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)',
        'items?task=t-1&conversation=c-1',
      ),
      'omi://h.omi.me/items?task=t-1&conversation=c-1',
    );
    assert.ok(
      isMacDesktopUserAgent(
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15',
      ),
    );
    assert.ok(
      !isMacDesktopUserAgent('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)'),
    );
    assert.ok(!isMacDesktopUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64)'));
    assert.match(macButton, /maxTouchPoints/);
    assert.match(macButton, /Open in Omi for Mac/);
  });

  it('give link previews generic Omi metadata with the count only', () => {
    const meta = itemListMetadata(3);
    assert.deepEqual(meta.title, { absolute: 'Omi' });
    assert.equal(meta.openGraph.title, 'Omi');
    assert.equal(meta.description, '3 items in Omi');
    assert.equal(meta.openGraph.description, '3 items in Omi');
    assert.deepEqual(meta.robots, { index: false, follow: false });
    assert.equal(itemListMetadata(0).description, ITEM_LINK_METADATA.description);
    assert.match(
      itemListPage,
      /itemListMetadata\(\(await itemsFor\(props\.searchParams\)\)\.length\)/,
    );
  });

  it('never read the items and never echo ids as HTML', () => {
    for (const source of [itemListPage, macButton]) {
      assert.doesNotMatch(source, /\bfetch\(|API_URL|sharedApiUrl|actions\//);
      assert.doesNotMatch(source, /dangerouslySetInnerHTML|innerHTML/);
    }
  });

  it('get the raw query from the proxy, which overwrites any client copy', () => {
    assert.equal(ITEM_LIST_QUERY_HEADER, 'x-omi-item-list-query');
    assert.match(proxySource, /'\/items'/);
    assert.match(proxySource, /forwarded\.set\(ITEM_LIST_QUERY_HEADER/);
  });

  it('are universal links for the app', () => {
    const paths = aasa.applinks.details[0].components.map((c) => c['/']);
    assert.ok(paths.includes('/items'));
  });
});
