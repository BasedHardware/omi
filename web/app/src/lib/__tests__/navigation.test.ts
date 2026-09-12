import { describe, expect, it } from 'vitest';
import { NAV_ITEMS, navItemsFor } from '../navigation';

describe('navigation SSOT', () => {
  it('derives both surfaces from the same list without duplicates', () => {
    const sidebar = navItemsFor('sidebar').map((i) => i.href);
    const bottomBar = navItemsFor('bottom-bar').map((i) => i.href);

    expect(new Set(sidebar).size).toBe(sidebar.length);
    expect(new Set(bottomBar).size).toBe(bottomBar.length);

    // Both surfaces agree on order and hrefs for shared destinations.
    const sharedBottom = bottomBar.filter((href) => sidebar.includes(href));
    expect(sharedBottom).toEqual(sidebar.filter((href) => bottomBar.includes(href)));
  });

  it('keeps Record off the sidebar rail and Memories off the bottom bar', () => {
    const sidebarHrefs = navItemsFor('sidebar').map((i) => i.href);
    const bottomBarHrefs = navItemsFor('bottom-bar').map((i) => i.href);

    expect(sidebarHrefs).not.toContain('/record');
    expect(bottomBarHrefs).not.toContain('/memories');

    // Both surfaces carry the core destinations.
    for (const href of ['/home', '/conversations', '/tasks']) {
      expect(sidebarHrefs).toContain(href);
      expect(bottomBarHrefs).toContain(href);
    }

    expect(sidebarHrefs.filter((href) => !bottomBarHrefs.includes(href))).toEqual([
      '/memories',
    ]);
  });

  it('gives every entry a label and falls back to it for the bottom bar', () => {
    for (const item of NAV_ITEMS) {
      expect(item.label.length).toBeGreaterThan(0);
      const bottomItem = navItemsFor('bottom-bar').find((i) => i.href === item.href);
      if (bottomItem) {
        expect(bottomItem.shortLabel ?? bottomItem.label).toBe(
          item.shortLabel ?? item.label,
        );
      }
    }
  });
});
