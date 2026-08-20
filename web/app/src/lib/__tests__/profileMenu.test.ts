import { describe, it, expect } from 'vitest';
import { PROFILE_MENU_MAX_HEIGHT, profileMenuHeightBound } from '@/lib/profileMenu';
import { SETTINGS_SECTIONS } from '@/lib/settingsSections';

/**
 * The profile menu opens by transitioning to a fixed max-height rather than to
 * `height: auto`, which needs no measurement but does need the ceiling to stay
 * above the content. Adding a settings section is the way this would silently
 * start clipping its own last row, so the ceiling is checked against the row
 * count the menu actually renders.
 */
describe('profile menu height ceiling', () => {
  it('clears the menu as it stands today', () => {
    expect(profileMenuHeightBound(SETTINGS_SECTIONS.length)).toBeLessThanOrEqual(
      PROFILE_MENU_MAX_HEIGHT,
    );
  });

  it('leaves room for two more settings sections before it needs raising', () => {
    expect(profileMenuHeightBound(SETTINGS_SECTIONS.length + 2)).toBeLessThanOrEqual(
      PROFILE_MENU_MAX_HEIGHT,
    );
  });

  it('grows with the row count, so the guard cannot pass vacuously', () => {
    expect(profileMenuHeightBound(6)).toBeGreaterThan(profileMenuHeightBound(3));
  });
});
