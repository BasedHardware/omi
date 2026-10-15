'use client';

import { AlertTriangle, Loader2 } from 'lucide-react';
import { DeveloperSection } from '@/components/settings/DeveloperSection';
import { useDeveloperSettings } from '@/hooks/useDeveloperSettings';
import { configuredApiBase } from '@/lib/agentPrompts';
import { AgentConnectSection } from './AgentConnectSection';

const QUICK_NAV = [
  { id: 'connect', label: 'Connect' },
  { id: 'api-keys', label: 'API Keys' },
  { id: 'mcp', label: 'MCP' },
  { id: 'webhooks', label: 'Webhooks' },
  { id: 'data-management', label: 'Data' },
];

/**
 * The one developer home every Omi client links to: connect an agent first,
 * then the key lists, MCP manual setup, webhooks, and data export that used
 * to live under Settings → Developer.
 */
export function DevelopersPage() {
  const developer = useDeveloperSettings();
  const apiBase = configuredApiBase();

  return (
    <div className="flex h-full flex-col">
      {developer.isExporting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60" />
          <div className="relative mx-4 w-full max-w-sm rounded-2xl border border-white/[0.06] bg-bg-secondary p-6 shadow-2xl">
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="rounded-full bg-white/[0.08] p-3">
                <Loader2 className="h-8 w-8 animate-spin text-text-secondary" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-text-primary">
                  Exporting Your Data
                </h3>
                <p className="mt-2 text-sm text-text-secondary">
                  This may take a moment depending on the amount of data in your account.
                </p>
              </div>
              <div className="flex items-center gap-2 rounded-xl bg-yellow-500/10 px-4 py-2">
                <AlertTriangle className="h-4 w-4 flex-shrink-0 text-yellow-400" />
                <span className="text-xs text-yellow-400">
                  Please don&apos;t close this tab
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      <main className="flex-1 overflow-y-auto pb-12">
        <div className="mx-auto max-w-4xl px-4 pt-16 sm:px-6 lg:px-8 lg:pt-6">
          <div className="flex gap-6">
            <div className="min-w-0 flex-1 space-y-12">
              <AgentConnectSection
                apiBase={apiBase}
                onCreateApiKey={developer.handleCreateApiKey}
                onCreateMcpKey={developer.handleCreateMcpKey}
              />
              {developer.isLoading ? (
                <div className="flex h-40 items-center justify-center">
                  <Loader2 className="h-8 w-8 animate-spin text-text-primary" />
                </div>
              ) : (
                <DeveloperSection
                  apiKeys={developer.apiKeys}
                  apiKeysError={developer.apiKeysError}
                  onRetryApiKeys={developer.loadApiKeys}
                  mcpKeysError={developer.mcpKeysError}
                  onRetryMcpKeys={developer.loadMcpKeys}
                  mcpKeys={developer.mcpKeys}
                  webhooks={developer.webhooks}
                  onCreateApiKey={developer.handleCreateApiKey}
                  onDeleteApiKey={developer.handleDeleteApiKey}
                  onCreateMcpKey={developer.handleCreateMcpKey}
                  onDeleteMcpKey={developer.handleDeleteMcpKey}
                  onWebhookChange={developer.handleWebhookChange}
                  onExportData={developer.handleExportData}
                  isExporting={developer.isExporting}
                  onDeleteKnowledgeGraph={developer.handleDeleteKnowledgeGraph}
                />
              )}
            </div>

            <div className="hidden w-32 flex-shrink-0 lg:block">
              <div className="sticky top-4">
                <p className="mb-3 text-xs font-medium uppercase tracking-wider text-text-quaternary">
                  On this page
                </p>
                <nav className="space-y-1">
                  {QUICK_NAV.map((section) => (
                    <a
                      key={section.id}
                      href={`#${section.id}`}
                      className="block py-1 text-sm text-text-tertiary transition-colors hover:text-text-primary"
                    >
                      {section.label}
                    </a>
                  ))}
                </nav>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
