'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
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
        'relative h-6 w-11 flex-shrink-0 rounded-full transition-all duration-200',
        enabled ? 'bg-white' : 'bg-white/[0.08]',
        disabled && 'cursor-not-allowed opacity-50',
      )}
    >
      <div
        className={cn(
          'absolute top-0.5 h-5 w-5 rounded-full shadow-sm transition-all duration-200',
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
      className={cn('rounded-section border border-stroke bg-bg-tertiary p-5', className)}
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
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const pollingRunRef = useRef(0);
  const pollingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollingDeadlineRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async (): Promise<Integration[]> => {
    const loaded = await getIntegrations();
    if (mountedRef.current) setIntegrations(loaded);
    return loaded;
  }, []);

  const stopPolling = useCallback(() => {
    pollingRunRef.current += 1;
    if (pollingTimeoutRef.current !== null) {
      clearTimeout(pollingTimeoutRef.current);
      pollingTimeoutRef.current = null;
    }
    if (pollingDeadlineRef.current !== null) {
      clearTimeout(pollingDeadlineRef.current);
      pollingDeadlineRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (integrationId: string) => {
      stopPolling();
      const run = pollingRunRef.current;

      const poll = async () => {
        if (!mountedRef.current || pollingRunRef.current !== run) return;

        try {
          const loaded = await refresh();
          if (!mountedRef.current || pollingRunRef.current !== run) return;
          setError(null);
          if (
            loaded.some(
              (integration) => integration.id === integrationId && integration.connected,
            )
          ) {
            stopPolling();
            return;
          }
        } catch (error) {
          if (!mountedRef.current || pollingRunRef.current !== run) return;
          console.error('Failed to refresh integrations:', error);
          setError('Could not refresh external services. Please try again.');
        }

        if (!mountedRef.current || pollingRunRef.current !== run) return;
        pollingTimeoutRef.current = setTimeout(poll, 3000);
      };

      pollingTimeoutRef.current = setTimeout(poll, 3000);
      pollingDeadlineRef.current = setTimeout(() => {
        if (!mountedRef.current || pollingRunRef.current !== run) return;
        stopPolling();
        setError('Connection timed out. Please try again.');
      }, 120000);
    },
    [refresh, stopPolling],
  );

  useEffect(() => {
    let active = true;
    mountedRef.current = true;
    refresh()
      .catch((error) => {
        if (!active) return;
        console.error('Failed to load integrations:', error);
        setError('Could not load external services. Please try again.');
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
      mountedRef.current = false;
      stopPolling();
    };
  }, [refresh, stopPolling]);

  const handleConnect = async (integration: Integration) => {
    if (integration.coming_soon || loadingId) return;

    const popup = window.open('', '_blank', 'width=600,height=700');
    if (!popup) {
      setError('Pop-up was blocked. Allow pop-ups and try again.');
      return;
    }

    setLoadingId(integration.id);
    setError(null);
    try {
      const authUrl = await getIntegrationOAuthUrl(integration.id);
      if (!authUrl) throw new Error('Could not start the connection.');
      // Open OAuth URL in new window
      popup.location.href = authUrl;
      // Note: User will complete OAuth in the popup, then we need to refresh
      // Set up a listener for when they return
      // Stop checking after 2 minutes
      startPolling(integration.id);
    } catch (error) {
      if (!popup.closed) popup.close();
      console.error('Failed to get OAuth URL:', error);
      setError(
        error instanceof Error ? error.message : 'Could not start the connection.',
      );
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
      setError(
        error instanceof Error ? error.message : 'Could not disconnect the service.',
      );
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
        <h2 className="text-lg font-medium text-text-primary">External services</h2>
        <p className="mt-1 text-sm text-text-tertiary">
          {summary.connected} of {summary.available} connected
        </p>
      </div>
      {error && <p className="text-sm text-error">{error}</p>}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-text-tertiary" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {integrations.map((integration) => (
            <Card
              key={integration.id}
              className={cn(integration.coming_soon && 'opacity-60')}
            >
              <div className="flex items-center gap-4">
                <div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-control bg-bg-quaternary">
                  {integration.icon.startsWith('/') ? (
                    <img
                      src={integration.icon}
                      alt={integration.name}
                      className="h-10 w-10 object-contain"
                    />
                  ) : (
                    <Puzzle className="h-6 w-6 text-text-secondary" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium text-text-primary">{integration.name}</h3>
                    {integration.coming_soon && (
                      <span className="rounded-chip bg-bg-quaternary px-2 py-0.5 text-xs text-text-tertiary">
                        Soon
                      </span>
                    )}
                    {integration.connected && !integration.coming_soon && (
                      <span className="rounded-chip bg-white/10 px-2 py-0.5 text-xs text-text-primary">
                        Connected
                      </span>
                    )}
                  </div>
                  <p className="truncate text-sm text-text-tertiary">
                    {integration.description}
                  </p>
                </div>
                {!integration.coming_soon &&
                  (loadingId === integration.id ? (
                    <Loader2 className="h-5 w-5 animate-spin text-text-tertiary" />
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="mx-4 max-w-md rounded-card border border-stroke bg-bg-secondary p-6 shadow-xl">
            <h3 className="mb-2 text-lg font-semibold text-text-primary">
              Disconnect {integrations.find((i) => i.id === showDisconnectConfirm)?.name}?
            </h3>
            <p className="mb-6 text-text-secondary">
              This will remove the connection. You can reconnect anytime.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowDisconnectConfirm(null)}
                className="rounded-control bg-bg-tertiary px-4 py-2 text-text-primary transition-colors hover:bg-bg-quaternary"
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
                className="rounded-control bg-red-500 px-4 py-2 text-white transition-colors hover:bg-red-600"
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
