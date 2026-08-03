import { describe, expect, it } from 'vitest';
import {
  SECTION_INFO,
  SETTINGS_SECTIONS,
  isSettingsSectionId,
} from '@/lib/settingsSections';

describe('SETTINGS_SECTIONS', () => {
  it('includes privacy, which shipped with no nav entry pointing at it', () => {
    expect(SETTINGS_SECTIONS.map((section) => section.id)).toContain('privacy');
  });

  it('gives every section a label and a description for the nav and header', () => {
    for (const section of SETTINGS_SECTIONS) {
      expect(section.label.length).toBeGreaterThan(0);
      expect(section.description.length).toBeGreaterThan(0);
    }
  });

  it('has no duplicate ids', () => {
    const ids = SETTINGS_SECTIONS.map((section) => section.id);

    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe('SECTION_INFO', () => {
  it('covers exactly the declared sections', () => {
    expect(Object.keys(SECTION_INFO).sort()).toEqual(
      SETTINGS_SECTIONS.map((section) => section.id).sort(),
    );
  });
});

describe('isSettingsSectionId', () => {
  it('accepts a declared section', () => {
    expect(isSettingsSectionId('privacy')).toBe(true);
  });

  it('rejects anything else, so ?section= cannot select a missing page', () => {
    expect(isSettingsSectionId('nope')).toBe(false);
    expect(isSettingsSectionId('')).toBe(false);
    expect(isSettingsSectionId('__proto__')).toBe(false);
  });
});
