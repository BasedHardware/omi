'use client';

import { useState, useEffect } from 'react';
import {
  Check,
  Copy,
  X,
  Plus,
  Trash2,
  MessageSquare,
  FileText,
  Radio,
  Calendar,
  ExternalLink,
  Loader2,
  Download,
  Network,
  AlertTriangle,
  BookOpen,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { DeveloperApiKey, McpApiKey, DeveloperWebhooks } from '@/types/user';
import { Toggle } from './SettingsToggle';
import { Card } from './SettingsCard';
import { McpSection } from './McpSection';

const SCOPE_RESOURCES = ['Conversations', 'Memories', 'Action Items', 'Goals'];
const scopeSelection = (mode: 'none' | 'read' | 'full') =>
  Object.fromEntries(
    SCOPE_RESOURCES.flatMap((resource) => {
      const key = resource.toLowerCase().replace(' ', '_');
      return [
        [`${key}:read`, mode !== 'none'],
        [`${key}:write`, mode === 'full'],
      ];
    }),
  );

// Create API Key Dialog
function CreateApiKeyDialog({
  isOpen,
  onClose,
  onCreateKey,
}: {
  isOpen: boolean;
  onClose: () => void;
  onCreateKey: (name: string, scopes: string[]) => Promise<DeveloperApiKey | null>;
}) {
  const [keyName, setKeyName] = useState('');
  const [scopes, setScopes] = useState<Record<string, boolean>>(() =>
    scopeSelection('none'),
  );
  const [isCreating, setIsCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<DeveloperApiKey | null>(null);
  const [copied, setCopied] = useState(false);

  const selectedScopes = Object.entries(scopes)
    .filter(([, v]) => v)
    .map(([k]) => k);
  const isReadOnly = Object.entries(scopes).every(
    ([key, selected]) => selected === key.endsWith(':read'),
  );
  const isFullAccess = Object.values(scopes).every(Boolean);
  const selectReadOnly = () => setScopes(scopeSelection('read'));
  const selectFullAccess = () => setScopes(scopeSelection('full'));

  const handleCreate = async () => {
    if (!keyName.trim() || selectedScopes.length === 0 || isCreating) return;
    setIsCreating(true);
    const key = await onCreateKey(keyName.trim(), selectedScopes);
    if (key) {
      setCreatedKey(key);
    }
    setIsCreating(false);
  };

  const handleCopy = () => {
    if (createdKey?.key) {
      navigator.clipboard.writeText(createdKey.key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleClose = () => {
    setKeyName('');
    setScopes(scopeSelection('none'));
    setCreatedKey(null);
    setCopied(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={handleClose}
    >
      <div
        className="mx-4 w-full max-w-md overflow-hidden rounded-2xl bg-bg-secondary"
        onClick={(e) => e.stopPropagation()}
      >
        {createdKey ? (
          <div className="p-6">
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-xl bg-green-500/20 p-3">
                <Check className="h-6 w-6 text-green-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-text-primary">
                  API Key Created
                </h3>
                <p className="text-sm text-text-tertiary">
                  Save this key now - you won&apos;t see it again!
                </p>
              </div>
            </div>
            <div className="mb-4 rounded-xl bg-bg-tertiary p-4">
              <p className="mb-2 text-xs text-text-tertiary">Your API Key</p>
              <code className="break-all font-mono text-sm text-text-primary">
                {createdKey.key}
              </code>
            </div>
            <div className="flex gap-3">
              <button
                onClick={handleCopy}
                className={cn(
                  'flex flex-1 items-center justify-center gap-2 rounded-xl px-4 py-3 font-medium transition-colors',
                  copied
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-text-primary text-bg-primary hover:bg-text-primary/90',
                )}
              >
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {copied ? 'Copied!' : 'Copy Key'}
              </button>
              <button
                onClick={handleClose}
                className="rounded-xl bg-bg-tertiary px-4 py-3 text-text-secondary transition-colors hover:bg-bg-quaternary"
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <div className="p-6">
            <div className="mb-6 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-text-primary">Create API Key</h3>
              <button
                onClick={handleClose}
                className="rounded-lg p-2 transition-colors hover:bg-bg-tertiary"
              >
                <X className="h-5 w-5 text-text-tertiary" />
              </button>
            </div>

            <div className="space-y-6">
              <div>
                <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                  Key Name
                </label>
                <input
                  type="text"
                  value={keyName}
                  onChange={(e) => setKeyName(e.target.value)}
                  placeholder="e.g., My App Integration"
                  className="w-full rounded-xl border border-white/[0.06] bg-bg-tertiary px-4 py-3 text-text-primary placeholder:text-text-quaternary focus:border-white/25 focus:outline-none"
                />
              </div>

              <div>
                <div className="mb-3 flex items-center justify-between">
                  <label className="text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                    Permissions
                  </label>
                  <div className="flex gap-2">
                    <button
                      onClick={selectReadOnly}
                      className={cn(
                        'rounded-full px-3 py-1.5 text-xs font-medium transition-colors',
                        isReadOnly
                          ? 'bg-text-primary text-bg-primary'
                          : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary',
                      )}
                    >
                      Read Only
                    </button>
                    <button
                      onClick={selectFullAccess}
                      className={cn(
                        'rounded-full px-3 py-1.5 text-xs font-medium transition-colors',
                        isFullAccess
                          ? 'bg-text-primary text-bg-primary'
                          : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary',
                      )}
                    >
                      Full Access
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  {SCOPE_RESOURCES.map((resource) => {
                    const readKey = `${resource.toLowerCase().replace(' ', '_')}:read`;
                    const writeKey = `${resource.toLowerCase().replace(' ', '_')}:write`;
                    return (
                      <div
                        key={resource}
                        className="flex items-center justify-between rounded-xl bg-bg-tertiary p-3"
                      >
                        <span className="text-sm text-text-primary">{resource}</span>
                        <div className="flex overflow-hidden rounded-lg bg-bg-quaternary">
                          <button
                            onClick={() =>
                              setScopes({ ...scopes, [readKey]: !scopes[readKey] })
                            }
                            aria-pressed={scopes[readKey]}
                            aria-label={`${resource} read permission`}
                            className={cn(
                              'px-3 py-1.5 text-xs font-semibold transition-colors',
                              scopes[readKey]
                                ? 'bg-blue-500 text-white'
                                : 'text-text-quaternary hover:text-text-secondary',
                            )}
                          >
                            R
                          </button>
                          <button
                            onClick={() =>
                              setScopes({ ...scopes, [writeKey]: !scopes[writeKey] })
                            }
                            aria-pressed={scopes[writeKey]}
                            aria-label={`${resource} write permission`}
                            className={cn(
                              'px-3 py-1.5 text-xs font-semibold transition-colors',
                              scopes[writeKey]
                                ? 'bg-text-primary text-bg-primary'
                                : 'text-text-quaternary hover:text-text-secondary',
                            )}
                          >
                            W
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <p className="mt-2 text-xs text-text-quaternary">
                  R = Read, W = Write. Select at least one permission to create a key.
                </p>
              </div>

              <button
                onClick={handleCreate}
                disabled={!keyName.trim() || selectedScopes.length === 0 || isCreating}
                className={cn(
                  'w-full rounded-xl py-3 font-medium transition-colors',
                  keyName.trim() && selectedScopes.length > 0 && !isCreating
                    ? 'bg-text-primary text-bg-primary hover:bg-text-primary/90'
                    : 'cursor-not-allowed bg-bg-tertiary text-text-quaternary',
                )}
              >
                {isCreating ? 'Creating...' : 'Create Key'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function DeveloperSection({
  apiKeys,
  apiKeysError,
  onRetryApiKeys,
  mcpKeysError,
  onRetryMcpKeys,
  mcpKeys,
  webhooks,
  onCreateApiKey,
  onDeleteApiKey,
  onCreateMcpKey,
  onDeleteMcpKey,
  onWebhookChange,
  onExportData,
  isExporting,
  onDeleteKnowledgeGraph,
}: {
  apiKeys: DeveloperApiKey[];
  apiKeysError: boolean;
  onRetryApiKeys: () => void;
  mcpKeysError: boolean;
  onRetryMcpKeys: () => void;
  mcpKeys: McpApiKey[];
  webhooks: DeveloperWebhooks;
  onCreateApiKey: (name: string, scopes: string[]) => Promise<DeveloperApiKey | null>;
  onDeleteApiKey: (keyId: string) => void;
  onCreateMcpKey: (name: string) => Promise<McpApiKey | null>;
  onDeleteMcpKey: (keyId: string) => void;
  onWebhookChange: (type: string, enabled: boolean, url?: string, delay?: string) => void;
  onExportData: () => void;
  isExporting?: boolean;
  onDeleteKnowledgeGraph: () => void;
}) {
  const [showApiKeyDialog, setShowApiKeyDialog] = useState(false);
  const [showDeleteGraphDialog, setShowDeleteGraphDialog] = useState(false);

  // Parse audio_bytes URL which may contain comma-separated URL and delay (e.g., "https://example.com,5")
  const parseAudioBytesUrl = (rawUrl: string) => {
    if (!rawUrl) return { url: '', delay: '5' };
    const parts = rawUrl.split(',');
    if (parts.length >= 2) {
      return { url: parts[0], delay: parts[1] };
    }
    return { url: rawUrl, delay: '5' };
  };

  const initialAudioBytes = parseAudioBytesUrl(webhooks.audio_bytes?.url || '');

  const [webhookUrls, setWebhookUrls] = useState<Record<string, string>>({
    memory_created: webhooks.memory_created?.url || '',
    transcript_received: webhooks.transcript_received?.url || '',
    audio_bytes: initialAudioBytes.url,
    day_summary: webhooks.day_summary?.url || '',
  });
  const [audioBytesDelay, setAudioBytesDelay] = useState(initialAudioBytes.delay);

  // Update webhook URLs when webhooks prop changes
  useEffect(() => {
    const audioBytes = parseAudioBytesUrl(webhooks.audio_bytes?.url || '');
    setWebhookUrls({
      memory_created: webhooks.memory_created?.url || '',
      transcript_received: webhooks.transcript_received?.url || '',
      audio_bytes: audioBytes.url,
      day_summary: webhooks.day_summary?.url || '',
    });
    setAudioBytesDelay(audioBytes.delay);
  }, [webhooks]);

  const webhookTypes = [
    {
      id: 'memory_created',
      label: 'Conversation Events',
      description: 'New conversation created',
      icon: MessageSquare,
    },
    {
      id: 'transcript_received',
      label: 'Real-time Transcript',
      description: 'Transcript received',
      icon: FileText,
    },
    {
      id: 'audio_bytes',
      label: 'Audio Bytes',
      description: 'Audio data received',
      icon: Radio,
      hasDelay: true,
    },
    {
      id: 'day_summary',
      label: 'Day Summary',
      description: 'Summary generated',
      icon: Calendar,
    },
  ];

  return (
    <div className="space-y-8">
      {/* Developer API Keys */}
      <div id="api-keys" className="scroll-mt-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-text-tertiary">
            Developer API Keys
          </h3>
          <button
            onClick={() => setShowApiKeyDialog(true)}
            className="flex items-center gap-1.5 rounded-full bg-white/[0.08] px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-white/[0.14]"
          >
            <Plus className="h-3 w-3" />
            Create Key
          </button>
        </div>
        <Card>
          {apiKeys.length > 0 ? (
            <div className="space-y-3">
              {apiKeys.map((apiKey) => (
                <div
                  key={apiKey.id}
                  className="flex items-center justify-between rounded-xl bg-bg-tertiary p-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-text-primary">
                        {apiKey.name}
                      </span>
                      <code className="rounded bg-bg-quaternary px-2 py-0.5 font-mono text-xs text-text-tertiary">
                        {apiKey.key_prefix}...
                      </code>
                      {apiKey.scopes && apiKey.scopes.length > 0 && (
                        <span className="rounded bg-white/[0.08] px-2 py-0.5 text-xs text-text-secondary">
                          {apiKey.scopes.length} scopes
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-text-quaternary">
                      Created {new Date(apiKey.created_at).toLocaleDateString()}
                      {apiKey.last_used_at &&
                        ` • Last used ${new Date(
                          apiKey.last_used_at,
                        ).toLocaleDateString()}`}
                    </p>
                  </div>
                  <button
                    aria-label={`Delete API key ${apiKey.name}`}
                    onClick={() => onDeleteApiKey(apiKey.id)}
                    className="rounded-lg p-2 text-text-secondary transition-colors hover:bg-red-500/10 hover:text-red-400"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          ) : apiKeysError ? (
            <div
              role="alert"
              className="space-y-3 py-6 text-center text-sm text-text-secondary"
            >
              <p>Failed to load API keys. Please try again.</p>
              <button
                onClick={onRetryApiKeys}
                className="rounded-full bg-white/[0.08] px-3 py-1.5 text-xs font-medium hover:bg-white/[0.14]"
              >
                Retry
              </button>
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-text-quaternary">
              No API keys created yet
            </p>
          )}
        </Card>
      </div>

      {/* MCP Section */}
      <McpSection
        mcpKeys={mcpKeys}
        listError={mcpKeysError}
        onRetry={onRetryMcpKeys}
        onCreateMcpKey={onCreateMcpKey}
        onDeleteMcpKey={onDeleteMcpKey}
      />

      {/* Webhooks */}
      <div id="webhooks" className="scroll-mt-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-text-tertiary">
            Webhooks
          </h3>
          <a
            href="https://docs.omi.me/doc/developer/apps/Introduction"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-text-secondary transition-colors hover:text-text-secondary"
          >
            Docs ↗
          </a>
        </div>
        <Card>
          <div className="space-y-1">
            {webhookTypes.map((webhook, index) => {
              const webhookData = webhooks[webhook.id as keyof DeveloperWebhooks];
              const isEnabled = webhookData?.enabled || false;
              const Icon = webhook.icon;

              return (
                <div key={webhook.id}>
                  {index > 0 && <div className="my-4 border-t border-white/[0.06]" />}
                  <div className="py-2">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="rounded-lg bg-bg-tertiary p-2">
                          <Icon className="h-4 w-4 text-text-tertiary" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-text-primary">
                            {webhook.label}
                          </p>
                          <p className="text-xs text-text-tertiary">
                            {webhook.description}
                          </p>
                        </div>
                      </div>
                      <Toggle
                        enabled={isEnabled}
                        label={`${webhook.label} webhook`}
                        onChange={(enabled) =>
                          onWebhookChange(
                            webhook.id,
                            enabled,
                            webhookUrls[webhook.id],
                            webhook.hasDelay ? audioBytesDelay : undefined,
                          )
                        }
                      />
                    </div>
                    {isEnabled && (
                      <div className="mt-3 space-y-2">
                        <input
                          type="url"
                          value={webhookUrls[webhook.id] || ''}
                          onChange={(e) =>
                            setWebhookUrls({
                              ...webhookUrls,
                              [webhook.id]: e.target.value,
                            })
                          }
                          onBlur={() =>
                            onWebhookChange(
                              webhook.id,
                              true,
                              webhookUrls[webhook.id],
                              webhook.hasDelay ? audioBytesDelay : undefined,
                            )
                          }
                          placeholder="https://your-server.com/webhook"
                          className="w-full rounded-lg border border-white/[0.06] bg-bg-tertiary px-3 py-2 text-sm text-text-primary placeholder:text-text-quaternary focus:border-white/25 focus:outline-none"
                        />
                        {webhook.hasDelay && (
                          <input
                            type="number"
                            value={audioBytesDelay}
                            onChange={(e) => setAudioBytesDelay(e.target.value)}
                            onBlur={() =>
                              onWebhookChange(
                                webhook.id,
                                true,
                                webhookUrls[webhook.id],
                                audioBytesDelay,
                              )
                            }
                            placeholder="Interval (seconds)"
                            className="w-full rounded-lg border border-white/[0.06] bg-bg-tertiary px-3 py-2 text-sm text-text-primary placeholder:text-text-quaternary focus:border-white/25 focus:outline-none"
                          />
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      {/* Data Management */}
      <div id="data-management" className="scroll-mt-4 space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-text-tertiary">
          Data Management
        </h3>
        <Card>
          <button
            onClick={onExportData}
            disabled={isExporting}
            className={cn(
              'flex w-full items-center gap-4 py-3 transition-colors',
              isExporting
                ? 'cursor-not-allowed text-text-tertiary'
                : 'text-text-primary hover:text-text-secondary',
            )}
          >
            <div className="rounded-lg bg-bg-tertiary p-2">
              {isExporting ? (
                <Loader2 className="h-5 w-5 animate-spin text-text-tertiary" />
              ) : (
                <Download className="h-5 w-5 text-text-tertiary" />
              )}
            </div>
            <div className="flex-1 text-left">
              <p className="font-medium">
                {isExporting ? 'Exporting...' : 'Export All Data'}
              </p>
              <p className="text-xs text-text-tertiary">
                {isExporting
                  ? 'This may take a moment'
                  : 'Export conversations to a JSON file'}
              </p>
            </div>
            {!isExporting && <ExternalLink className="h-4 w-4 text-text-quaternary" />}
          </button>
        </Card>
        <Card className="border-red-500/20">
          <button
            onClick={() => setShowDeleteGraphDialog(true)}
            className="flex w-full items-center gap-4 py-3 text-text-primary transition-colors hover:text-red-400"
          >
            <div className="rounded-lg bg-red-500/10 p-2">
              <Network className="h-5 w-5 text-red-400" />
            </div>
            <div className="flex-1 text-left">
              <p className="font-medium">Delete Knowledge Graph</p>
              <p className="text-xs text-text-tertiary">
                Clear all nodes and connections
              </p>
            </div>
            <Trash2 className="h-4 w-4 text-text-quaternary" />
          </button>
        </Card>
      </div>

      {/* Links */}
      <Card>
        <a
          href="https://docs.omi.me"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-between py-3 text-text-primary transition-colors hover:text-text-secondary"
        >
          <div className="flex items-center gap-3">
            <BookOpen className="h-5 w-5 text-text-tertiary" />
            <span>API Documentation</span>
          </div>
          <ExternalLink className="h-4 w-4" />
        </a>
      </Card>

      {/* Dialogs */}
      <CreateApiKeyDialog
        isOpen={showApiKeyDialog}
        onClose={() => setShowApiKeyDialog(false)}
        onCreateKey={onCreateApiKey}
      />

      {/* Delete Knowledge Graph Dialog */}
      {showDeleteGraphDialog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          onClick={() => setShowDeleteGraphDialog(false)}
        >
          <div
            className="mx-4 w-full max-w-md rounded-2xl bg-bg-secondary p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center gap-3">
              <div className="rounded-xl bg-red-500/20 p-3">
                <AlertTriangle className="h-6 w-6 text-red-400" />
              </div>
              <h3 className="text-lg font-semibold text-text-primary">
                Delete Knowledge Graph?
              </h3>
            </div>
            <p className="mb-6 text-sm text-text-secondary">
              This will delete all derived knowledge graph data (nodes and connections).
              Your original memories will remain safe. The graph will be rebuilt over
              time.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowDeleteGraphDialog(false)}
                className="flex-1 rounded-xl bg-bg-tertiary py-3 text-text-secondary transition-colors hover:bg-bg-quaternary"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  onDeleteKnowledgeGraph();
                  setShowDeleteGraphDialog(false);
                }}
                className="flex-1 rounded-xl bg-red-500 py-3 text-white transition-colors hover:bg-red-600"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
