import { describe, expect, it } from 'vitest';
import {
  MESSAGING_CHANNELS,
  channelLabel,
  connectorTabFromParam,
  isChannelLinked,
  summarizeIntegrations,
} from '@/lib/connectors';
import type { Integration } from '@/types/user';

function integration(overrides: Partial<Integration>): Integration {
  return {
    id: 'x',
    name: 'X',
    description: '',
    icon: '',
    connected: false,
    ...overrides,
  };
}

describe('channelLabel', () => {
  it('capitalizes iMessage the way Apple does, not the way the id is stored', () => {
    expect(channelLabel('imessage')).toBe('iMessage');
  });

  it('labels every declared channel', () => {
    for (const channel of MESSAGING_CHANNELS) {
      expect(channelLabel(channel).length).toBeGreaterThan(0);
    }
  });

  it('falls back to a capitalized id for a channel the backend adds later', () => {
    expect(channelLabel('whatsapp')).toBe('Whatsapp');
  });
});

describe('isChannelLinked', () => {
  it('is false before the status has loaded', () => {
    expect(isChannelLinked(null, 'telegram')).toBe(false);
  });

  it('matches only the requested channel', () => {
    const status = {
      bindings: [{ channel: 'telegram', linked_at: 'now' }],
      phone_registered: false,
    };

    expect(isChannelLinked(status, 'telegram')).toBe(true);
    expect(isChannelLinked(status, 'sms')).toBe(false);
  });
});

describe('connectorTabFromParam', () => {
  it('selects the services group, which the channel-link redirect lands on', () => {
    expect(connectorTabFromParam('services')).toBe('services');
  });

  it('falls back to explore for a missing or unknown tab', () => {
    expect(connectorTabFromParam(null)).toBe('explore');
    expect(connectorTabFromParam('integrations')).toBe('explore');
    expect(connectorTabFromParam('__proto__')).toBe('explore');
  });
});

describe('summarizeIntegrations', () => {
  it('excludes coming-soon services, which offer no control', () => {
    expect(
      summarizeIntegrations([
        integration({ id: 'a', connected: true }),
        integration({ id: 'b', connected: false }),
        integration({ id: 'c', connected: false, coming_soon: true }),
      ]),
    ).toEqual({ connected: 1, available: 2 });
  });

  it('handles an empty list', () => {
    expect(summarizeIntegrations([])).toEqual({ connected: 0, available: 0 });
  });
});
