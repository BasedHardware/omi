import type { ChannelStatus } from '@/lib/api';
import type { Integration } from '@/types/user';

/**
 * The messaging channels Omi core chat can be reached from, in display order.
 */
export const MESSAGING_CHANNELS = ['telegram', 'imessage', 'sms'] as const;

export type MessagingChannel = (typeof MESSAGING_CHANNELS)[number];

const CHANNEL_LABELS: Record<MessagingChannel, string> = {
  telegram: 'Telegram',
  imessage: 'iMessage',
  sms: 'SMS',
};

export function channelLabel(channel: string): string {
  return (
    CHANNEL_LABELS[channel as MessagingChannel] ??
    channel.charAt(0).toUpperCase() + channel.slice(1)
  );
}

export function isChannelLinked(status: ChannelStatus | null, channel: string): boolean {
  return Boolean(status?.bindings.some((binding) => binding.channel === channel));
}

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
