import { describe, expect, it } from 'vitest';
import { connectorTabFromParam, summarizeIntegrations } from '@/lib/connectors';
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

describe('connectorTabFromParam', () => {
  it('selects the services group', () => {
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
