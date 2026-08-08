import type { Integration } from '@/types/user';

/**
 * The Connectors page groups, in tab order: the app catalogue, the apps the
 * user installed, the apps they built, and the external services that used to
 * live under Settings → Integrations.
 */
export const CONNECTOR_TABS = ['explore', 'installed', 'my-apps', 'services'] as const;

export type ConnectorTab = (typeof CONNECTOR_TABS)[number];

export function connectorTabFromParam(value: string | null): ConnectorTab {
  return CONNECTOR_TABS.includes(value as ConnectorTab)
    ? (value as ConnectorTab)
    : 'explore';
}

export interface ConnectorSummary {
  connected: number;
  available: number;
}

/**
 * Counts what the Connectors page can say about external services: services
 * currently connected, and services that can be connected right now. A
 * `coming_soon` service is neither — it has no control the user can act on.
 */
export function summarizeIntegrations(integrations: Integration[]): ConnectorSummary {
  const actionable = integrations.filter((integration) => !integration.coming_soon);

  return {
    connected: actionable.filter((integration) => integration.connected).length,
    available: actionable.length,
  };
}
