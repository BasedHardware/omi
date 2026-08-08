'use client';

import { useCallback, useEffect, useState } from 'react';
import { Loader2, Puzzle } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  disconnectIntegration,
  getIntegrationOAuthUrl,
  getIntegrations,
} from '@/lib/api';
import { summarizeIntegrations } from '@/lib/connectors';
import type { Integration } from '@/types/user';

function Toggle({
  enabled,
  onChange,
  disabled = false,
}: {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      className={cn(
        'relative w-11 h-6 rounded-full transition-all duration-200 flex-shrink-0',
        enabled ? 'bg-white' : 'bg-white/[0.08]',
        disabled && 'opacity-50 cursor-not-allowed',
      )}
    >
      <div
        className={cn(
          'absolute top-0.5 w-5 h-5 rounded-full transition-all duration-200 shadow-sm',
          enabled ? 'left-[22px] bg-black' : 'left-0.5 bg-white',
        )}
      />
    </button>
  );
}

function Card({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn('rounded-section p-5 bg-bg-tertiary border border-stroke', className)}
    >
      {children}
    </div>
  );
}

export function ConnectedServices() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const loaded = await getIntegrations().catch(() => []);
    setIntegrations(loaded);
  }, []);

  useEffect(() => {
    let active = true;
    refresh().finally(() => {
      if (active) setIsLoading(false);
    });
    return () => {
      active = false;
    };
  }, [refresh]);

  const handleConnect = async (integration: Integration) => {
    if (integration.coming_soon || loadingId) return;

    setLoadingId(integration.id);
    try {
      const authUrl = await getIntegrationOAuthUrl(integration.id);
      if (authUrl) {
        // Open OAuth URL in new window
        window.open(authUrl, '_blank', 'width=600,height=700');
        // Note: User will complete OAuth in the popup, then we need to refresh
        // Set up a listener for when they return
        const checkConnection = setInterval(async () => {
          await refresh();
        }, 3000);
        // Stop checking after 2 minutes
        setTimeout(() => clearInterval(checkConnection), 120000);
      }
    } catch (error) {
      console.error('Failed to get OAuth URL:', error);
    } finally {
      setLoadingId(null);
    }
  };

  const handleDisconnect = async (integration: Integration) => {
    if (loadingId) return;

    setLoadingId(integration.id);
    setShowDisconnectConfirm(null);
    try {
      await disconnectIntegration(integration.id);
      await refresh();
    } catch (error) {
      console.error('Failed to disconnect:', error);
    } finally {
      setLoadingId(null);
    }
  };

  const handleToggle = (integration: Integration) => {
    if (integration.connected) {
      setShowDisconnectConfirm(integration.id);
    } else {
      handleConnect(integration);
    }
  };

  const summary = summarizeIntegrations(integrations);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-text-primary text-lg font-medium">External services</h2>
        <p className="text-sm text-text-tertiary mt-1">
          {summary.connected} of {summary.available} connected
        </p>
      </div>
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-6 h-6 text-text-tertiary animate-spin" />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {integrations.map((integration) => (
            <Card
              key={integration.id}
              className={cn(integration.coming_soon && 'opacity-60')}
            >
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-control overflow-hidden bg-bg-quaternary flex items-center justify-center">
                  {integration.icon.startsWith('/') ? (
                    <img
                      src={integration.icon}
                      alt={integration.name}
                      className="w-10 h-10 object-contain"
                    />
                  ) : (
                    <Puzzle className="w-6 h-6 text-text-secondary" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-text-primary font-medium">{integration.name}</h3>
                    {integration.coming_soon && (
                      <span className="px-2 py-0.5 rounded-chip text-xs bg-bg-quaternary text-text-tertiary">
                        Soon
                      </span>
                    )}
                    {integration.connected && !integration.coming_soon && (
                      <span className="px-2 py-0.5 rounded-chip text-xs bg-white/10 text-text-primary">
                        Connected
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-text-tertiary truncate">
                    {integration.description}
                  </p>
                </div>
                {!integration.coming_soon &&
                  (loadingId === integration.id ? (
                    <Loader2 className="w-5 h-5 animate-spin text-text-tertiary" />
                  ) : (
                    <Toggle
                      enabled={integration.connected}
                      onChange={() => handleToggle(integration)}
                    />
                  ))}
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Disconnect Confirmation Dialog */}
      {showDisconnectConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-bg-secondary rounded-card p-6 max-w-md mx-4 shadow-xl border border-stroke">
            <h3 className="text-lg font-semibold text-text-primary mb-2">
              Disconnect {integrations.find((i) => i.id === showDisconnectConfirm)?.name}?
            </h3>
            <p className="text-text-secondary mb-6">
              This will remove the connection. You can reconnect anytime.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowDisconnectConfirm(null)}
                className="px-4 py-2 rounded-control bg-bg-tertiary text-text-primary hover:bg-bg-quaternary transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  const integration = integrations.find(
                    (i) => i.id === showDisconnectConfirm,
                  );
                  if (integration) handleDisconnect(integration);
                }}
                className="px-4 py-2 rounded-control bg-red-500 text-white hover:bg-red-600 transition-colors"
              >
                Disconnect
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
