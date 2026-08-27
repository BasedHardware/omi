import { describe, expect, it } from 'vitest';
import {
  CLAUDE_CONNECTOR_OAUTH,
  SECTION_INFO,
  SETTINGS_SECTIONS,
  SIGNED_OUT_DESTINATION,
  isSettingsSectionId,
  toWebhookApiType,
  ACCOUNT_QUICK_NAV,
  DEVELOPER_QUICK_NAV,
} from '@/features/settings';

describe('CLAUDE_CONNECTOR_OAUTH', () => {
  it('uses the registered public PKCE client without a secret', () => {
    expect(CLAUDE_CONNECTOR_OAUTH).toEqual({
      clientId: 'omi-claude-prod',
      clientSecret: '',
    });
  });
});

describe('SIGNED_OUT_DESTINATION', () => {
  it('uses a registered client route after authentication ends', () => {
    expect(SIGNED_OUT_DESTINATION).toBe('/login');
  });
});

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

  it('has no integrations section — connected services live on /connectors', () => {
    expect(SETTINGS_SECTIONS.map((section) => section.id)).not.toContain('integrations');
  });

  it('has one merged account section rather than separate profile and account', () => {
    const ids = SETTINGS_SECTIONS.map((section) => section.id);

    expect(ids).toContain('account');
    expect(ids).not.toContain('profile');
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
    expect(isSettingsSectionId('integrations')).toBe(false);
    expect(isSettingsSectionId('profile')).toBe(false);
    expect(isSettingsSectionId('')).toBe(false);
    expect(isSettingsSectionId('__proto__')).toBe(false);
  });
});

describe('toWebhookApiType', () => {
  it('maps the UI transcript hook name to the API name', () => {
    expect(toWebhookApiType('transcript_received')).toBe('realtime_transcript');
  });

  it('leaves API names unchanged', () => {
    expect(toWebhookApiType('memory_created')).toBe('memory_created');
    expect(toWebhookApiType('audio_bytes')).toBe('audio_bytes');
    expect(toWebhookApiType('day_summary')).toBe('day_summary');
  });
});

describe('quick nav ids', () => {
  it('anchors the merged account page and developer page', () => {
    expect(ACCOUNT_QUICK_NAV.map((item) => item.id)).toEqual([
      'account-info',
      'language',
      'vocabulary',
      'notifications',
      'plan-usage',
      'fair-use',
      'actions',
      'support',
    ]);
    expect(DEVELOPER_QUICK_NAV.map((item) => item.id)).toEqual([
      'api-keys',
      'mcp',
      'webhooks',
      'data-management',
      'experimental',
    ]);
  });
});
