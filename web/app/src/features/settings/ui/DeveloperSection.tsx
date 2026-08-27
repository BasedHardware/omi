'use client';

import { useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import {
  Plus,
  Copy,
  Check,
  X,
  Download,
  FlaskConical,
  Loader2,
  ExternalLink,
  Trash2,
  Server,
  BookOpen,
  Monitor,
  Network,
  Activity,
  UserPlus,
  Lightbulb,
  Target,
  AlertTriangle,
  MessageSquare,
  FileText,
  Radio,
  Calendar,
} from 'lucide-react';
import { CLAUDE_CONNECTOR_OAUTH } from '../model';
import { API_KEY_SCOPES } from '@/types/user';
import type { DeveloperApiKey, McpApiKey, DeveloperWebhooks } from '@/types/user';
import { Card, SettingRow, Toggle, ConfirmDialog } from './settingsPrimitives';

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
  const [scopes, setScopes] = useState<Record<string, boolean>>({
    'conversations:read': false,
    'conversations:write': false,
    'memories:read': false,
    'memories:write': false,
    'action_items:read': false,
    'action_items:write': false,
  });
  const [isCreating, setIsCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<DeveloperApiKey | null>(null);
  const [copied, setCopied] = useState(false);

  const selectedScopes = Object.entries(scopes)
    .filter(([, v]) => v)
    .map(([k]) => k);
  const isReadOnly =
    scopes['conversations:read'] &&
    scopes['memories:read'] &&
    scopes['action_items:read'] &&
    !scopes['conversations:write'] &&
    !scopes['memories:write'] &&
    !scopes['action_items:write'];
  const isFullAccess = Object.values(scopes).every((v) => v);

  const selectReadOnly = () => {
    setScopes({
      'conversations:read': true,
      'conversations:write': false,
      'memories:read': true,
      'memories:write': false,
      'action_items:read': true,
      'action_items:write': false,
    });
  };

  const selectFullAccess = () => {
    setScopes(Object.fromEntries(Object.keys(scopes).map((k) => [k, true])));
  };

  const handleCreate = async () => {
    if (!keyName.trim()) return;
    setIsCreating(true);
    const key = await onCreateKey(
      keyName.trim(),
      selectedScopes.length > 0 ? selectedScopes : (undefined as unknown as string[]),
    );
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
    setScopes(Object.fromEntries(Object.keys(scopes).map((k) => [k, false])));
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
        className="bg-bg-secondary rounded-2xl w-full max-w-md mx-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {createdKey ? (
          <div className="p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-xl bg-green-500/20">
                <Check className="w-6 h-6 text-green-400" />
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
            <div className="p-4 rounded-xl bg-bg-tertiary mb-4">
              <p className="text-xs text-text-tertiary mb-2">Your API Key</p>
              <code className="text-sm text-text-primary font-mono break-all">
                {createdKey.key}
              </code>
            </div>
            <div className="flex gap-3">
              <button
                onClick={handleCopy}
                className={cn(
                  'flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-medium transition-colors',
                  copied
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-text-primary text-bg-primary hover:bg-text-primary/90',
                )}
              >
                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                {copied ? 'Copied!' : 'Copy Key'}
              </button>
              <button
                onClick={handleClose}
                className="px-4 py-3 rounded-xl bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <div className="p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-text-primary">Create API Key</h3>
              <button
                onClick={handleClose}
                className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors"
              >
                <X className="w-5 h-5 text-text-tertiary" />
              </button>
            </div>

            <div className="space-y-6">
              <div>
                <label className="block text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">
                  Key Name
                </label>
                <input
                  type="text"
                  value={keyName}
                  onChange={(e) => setKeyName(e.target.value)}
                  placeholder="e.g., My App Integration"
                  className="w-full px-4 py-3 rounded-xl bg-bg-tertiary border border-white/[0.06] text-text-primary placeholder:text-text-quaternary focus:outline-none focus:border-white/25"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-3">
                  <label className="text-xs font-semibold text-text-tertiary uppercase tracking-wider">
                    Permissions
                  </label>
                  <div className="flex gap-2">
                    <button
                      onClick={selectReadOnly}
                      className={cn(
                        'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
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
                        'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
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
                  {['Conversations', 'Memories', 'Action Items'].map((resource) => {
                    const readKey = `${resource.toLowerCase().replace(' ', '_')}:read`;
                    const writeKey = `${resource.toLowerCase().replace(' ', '_')}:write`;
                    return (
                      <div
                        key={resource}
                        className="flex items-center justify-between p-3 rounded-xl bg-bg-tertiary"
                      >
                        <span className="text-sm text-text-primary">{resource}</span>
                        <div className="flex bg-bg-quaternary rounded-lg overflow-hidden">
                          <button
                            onClick={() =>
                              setScopes({ ...scopes, [readKey]: !scopes[readKey] })
                            }
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
                <p className="text-xs text-text-quaternary mt-2">
                  R = Read, W = Write. Defaults to read-only if nothing selected.
                </p>
              </div>

              <button
                onClick={handleCreate}
                disabled={!keyName.trim() || isCreating}
                className={cn(
                  'w-full py-3 rounded-xl font-medium transition-colors',
                  keyName.trim() && !isCreating
                    ? 'bg-text-primary text-bg-primary hover:bg-text-primary/90'
                    : 'bg-bg-tertiary text-text-quaternary cursor-not-allowed',
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

// Create MCP Key Dialog
function CreateMcpKeyDialog({
  isOpen,
  onClose,
  onCreateKey,
}: {
  isOpen: boolean;
  onClose: () => void;
  onCreateKey: (name: string) => Promise<McpApiKey | null>;
}) {
  const [keyName, setKeyName] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<McpApiKey | null>(null);
  const [copied, setCopied] = useState(false);

  const handleCreate = async () => {
    if (!keyName.trim()) return;
    setIsCreating(true);
    const key = await onCreateKey(keyName.trim());
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
        className="bg-bg-secondary rounded-2xl w-full max-w-md mx-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {createdKey ? (
          <div className="p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-xl bg-green-500/20">
                <Check className="w-6 h-6 text-green-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-text-primary">
                  MCP Key Created
                </h3>
                <p className="text-sm text-text-tertiary">
                  Save this key now - you won&apos;t see it again!
                </p>
              </div>
            </div>
            <div className="p-4 rounded-xl bg-bg-tertiary mb-4">
              <p className="text-xs text-text-tertiary mb-2">Your MCP Key</p>
              <code className="text-sm text-text-primary font-mono break-all">
                {createdKey.key}
              </code>
            </div>
            <div className="flex gap-3">
              <button
                onClick={handleCopy}
                className={cn(
                  'flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-medium transition-colors',
                  copied
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-text-primary text-bg-primary hover:bg-text-primary/90',
                )}
              >
                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                {copied ? 'Copied!' : 'Copy Key'}
              </button>
              <button
                onClick={handleClose}
                className="px-4 py-3 rounded-xl bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <div className="p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-text-primary">Create MCP Key</h3>
              <button
                onClick={handleClose}
                className="p-2 rounded-lg hover:bg-bg-tertiary transition-colors"
              >
                <X className="w-5 h-5 text-text-tertiary" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">
                  Key Name
                </label>
                <input
                  type="text"
                  value={keyName}
                  onChange={(e) => setKeyName(e.target.value)}
                  placeholder="e.g., Claude Desktop"
                  className="w-full px-4 py-3 rounded-xl bg-bg-tertiary border border-white/[0.06] text-text-primary placeholder:text-text-quaternary focus:outline-none focus:border-white/25"
                />
              </div>
              <button
                onClick={handleCreate}
                disabled={!keyName.trim() || isCreating}
                className={cn(
                  'w-full py-3 rounded-xl font-medium transition-colors',
                  keyName.trim() && !isCreating
                    ? 'bg-text-primary text-bg-primary hover:bg-text-primary/90'
                    : 'bg-bg-tertiary text-text-quaternary cursor-not-allowed',
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
  const [showMcpKeyDialog, setShowMcpKeyDialog] = useState(false);
  const [showDeleteGraphDialog, setShowDeleteGraphDialog] = useState(false);
  const [copiedConfig, setCopiedConfig] = useState(false);
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [copiedClaudeName, setCopiedClaudeName] = useState(false);
  const [copiedClaudeUrl, setCopiedClaudeUrl] = useState(false);
  const [copiedClaudeClientId, setCopiedClaudeClientId] = useState(false);
  const [copiedClaudeSecret, setCopiedClaudeSecret] = useState(false);

  const mcpServerUrl = `${process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me'}/v1/mcp/sse`;

  // Claude connector values — mirror the 4 fields in Claude's "Add custom connector" form
  const claudeConnectorName = 'Omi Memory';
  const claudeConnectorUrl = mcpServerUrl;
  const claudeConnectorClientId = CLAUDE_CONNECTOR_OAUTH.clientId;
  const claudeConnectorSecret: string = CLAUDE_CONNECTOR_OAUTH.clientSecret;

  // Experimental features (stored in localStorage)
  const [experimentalFeatures, setExperimentalFeatures] = useState({
    transcriptionDiagnostics: false,
    autoCreateSpeakers: false,
    followUpQuestions: false,
    goalTracker: false,
  });

  // Load experimental features from localStorage on mount
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('omi_experimental_features');
      if (saved) {
        try {
          setExperimentalFeatures(JSON.parse(saved));
        } catch {
          // Ignore parse errors
        }
      }
    }
  }, []);

  // Save experimental features to localStorage when they change
  const updateExperimentalFeature = (
    key: keyof typeof experimentalFeatures,
    value: boolean,
  ) => {
    const updated = { ...experimentalFeatures, [key]: value };
    setExperimentalFeatures(updated);
    if (typeof window !== 'undefined') {
      localStorage.setItem('omi_experimental_features', JSON.stringify(updated));
    }
  };

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

  const claudeDesktopConfig = `{
  "mcpServers": {
    "omi": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "-e", "OMI_API_KEY=your_api_key_here", "omiai/mcp-server:latest"]
    }
  }
}`;

  const copyConfig = () => {
    navigator.clipboard.writeText(claudeDesktopConfig);
    setCopiedConfig(true);
    setTimeout(() => setCopiedConfig(false), 2000);
  };

  const copyUrl = () => {
    navigator.clipboard.writeText(mcpServerUrl);
    setCopiedUrl(true);
    setTimeout(() => setCopiedUrl(false), 2000);
  };

  return (
    <div className="space-y-8">
      {/* Developer API Keys */}
      <div id="api-keys" className="space-y-3 scroll-mt-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider">
            Developer API Keys
          </h3>
          <button
            onClick={() => setShowApiKeyDialog(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/[0.08] text-text-secondary text-xs font-medium hover:bg-white/[0.14] transition-colors"
          >
            <Plus className="w-3 h-3" />
            Create Key
          </button>
        </div>
        <Card>
          {apiKeys.length > 0 ? (
            <div className="space-y-3">
              {apiKeys.map((apiKey) => (
                <div
                  key={apiKey.id}
                  className="flex items-center justify-between p-3 rounded-xl bg-bg-tertiary"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm text-text-primary font-medium">
                        {apiKey.name}
                      </span>
                      <code className="text-xs text-text-tertiary font-mono bg-bg-quaternary px-2 py-0.5 rounded">
                        {apiKey.key_prefix}...
                      </code>
                      {apiKey.scopes && apiKey.scopes.length > 0 && (
                        <span className="text-xs text-text-secondary bg-white/[0.08] px-2 py-0.5 rounded">
                          {apiKey.scopes.length} scopes
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-text-quaternary mt-1">
                      Created {new Date(apiKey.created_at).toLocaleDateString()}
                      {apiKey.last_used_at &&
                        ` • Last used ${new Date(apiKey.last_used_at).toLocaleDateString()}`}
                    </p>
                  </div>
                  <button
                    onClick={() => onDeleteApiKey(apiKey.id)}
                    className="p-2 rounded-lg text-text-secondary hover:text-red-400 hover:bg-red-500/10 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-text-quaternary text-center py-6">
              No API keys created yet
            </p>
          )}
        </Card>
      </div>

      {/* MCP Section */}
      <div id="mcp" className="space-y-3 scroll-mt-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider">
              MCP
            </h3>
            <a
              href="https://docs.omi.me/doc/developer/MCP"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-text-secondary hover:text-text-secondary transition-colors"
            >
              Docs ↗
            </a>
          </div>
          <button
            onClick={() => setShowMcpKeyDialog(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/[0.08] text-text-secondary text-xs font-medium hover:bg-white/[0.14] transition-colors"
          >
            <Plus className="w-3 h-3" />
            Create Key
          </button>
        </div>

        {/* MCP Keys List */}
        <Card>
          {mcpKeys.length > 0 ? (
            <div className="space-y-3">
              {mcpKeys.map((key) => (
                <div
                  key={key.id}
                  className="flex items-center justify-between p-3 rounded-xl bg-bg-tertiary"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-text-primary font-medium">
                        {key.name}
                      </span>
                      <code className="text-xs text-text-tertiary font-mono bg-bg-quaternary px-2 py-0.5 rounded">
                        {key.key_prefix}...
                      </code>
                    </div>
                    <p className="text-xs text-text-quaternary mt-1">
                      Created {new Date(key.created_at).toLocaleDateString()}
                      {key.last_used_at &&
                        ` • Last used ${new Date(key.last_used_at).toLocaleDateString()}`}
                    </p>
                  </div>
                  <button
                    onClick={() => onDeleteMcpKey(key.id)}
                    className="p-2 rounded-lg text-text-secondary hover:text-red-400 hover:bg-red-500/10 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-text-quaternary text-center py-6">
              No MCP keys created yet
            </p>
          )}
        </Card>

        {/* Claude Desktop Config */}
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-bg-tertiary">
              <Monitor className="w-5 h-5 text-text-tertiary" />
            </div>
            <div>
              <p className="text-text-primary font-medium">Claude Desktop</p>
              <p className="text-xs text-text-tertiary">
                Add to claude_desktop_config.json
              </p>
            </div>
          </div>
          <div className="p-4 rounded-xl bg-[#0d0d0d] border border-white/[0.06] font-mono text-xs overflow-x-auto">
            <pre className="text-text-secondary whitespace-pre">
              {claudeDesktopConfig}
            </pre>
          </div>
          <button
            onClick={copyConfig}
            className={cn(
              'w-full mt-3 flex items-center justify-center gap-2 py-2.5 rounded-xl transition-colors',
              copiedConfig
                ? 'bg-green-500/20 text-green-400'
                : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary',
            )}
          >
            {copiedConfig ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            {copiedConfig ? 'Copied!' : 'Copy Config'}
          </button>
        </Card>

        {/* Generic MCP Server Info */}
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-bg-tertiary">
              <Server className="w-5 h-5 text-text-tertiary" />
            </div>
            <div>
              <p className="text-text-primary font-medium">MCP Server</p>
              <p className="text-xs text-text-tertiary">
                Connect ChatGPT, Codex, Claude, or any MCP client to your data
              </p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <p className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">
                Server URL
              </p>
              <button
                onClick={copyUrl}
                className="w-full flex items-center justify-between p-3 rounded-xl bg-[#0d0d0d] border border-white/[0.06] hover:border-white/25 transition-colors"
              >
                <code className="text-sm text-text-primary font-mono truncate mr-2">
                  {mcpServerUrl}
                </code>
                {copiedUrl ? (
                  <Check className="w-4 h-4 text-green-400 flex-shrink-0" />
                ) : (
                  <Copy className="w-4 h-4 text-text-quaternary flex-shrink-0" />
                )}
              </button>
            </div>

            <div className="border-t border-white/[0.06] pt-4">
              <p className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">
                API Key Auth
              </p>
              <div className="flex items-center gap-4 text-sm">
                <span className="text-text-tertiary">Header</span>
                <code className="text-text-quaternary font-mono text-xs">
                  Authorization: Bearer &lt;key&gt;
                </code>
              </div>
            </div>

            <div className="border-t border-white/[0.06] pt-4">
              <p className="text-xs font-semibold text-text-tertiary uppercase tracking-wider mb-2">
                OAuth
              </p>
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-4">
                  <span className="text-text-tertiary w-24">Client ID</span>
                  <code className="text-text-primary font-mono">omi</code>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-text-tertiary w-24">Client Secret</span>
                  <span className="text-text-quaternary italic text-xs">
                    Use your MCP API key
                  </span>
                </div>
              </div>
            </div>
          </div>
        </Card>

        {/* Claude Connector — 4 copy fields mirroring Claude's "Add custom connector" form */}
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <div className="w-12 h-12 rounded-xl overflow-hidden bg-gradient-to-br from-orange-500/20 to-orange-600/10 border border-orange-500/20 flex items-center justify-center flex-shrink-0">
              <span className="text-lg font-semibold text-orange-400">C</span>
            </div>
            <div>
              <p className="text-text-primary font-medium">Claude</p>
              <p className="text-xs text-text-tertiary">Live MCP or memory pack</p>
            </div>
          </div>

          <p className="text-sm text-text-secondary mb-4">
            Connect over MCP so Claude reads your memories live, or copy a memory pack.
            Each field below maps to Claude&rsquo;s{' '}
            <span className="text-text-tertiary">
              Settings → Connectors → Add custom connector
            </span>{' '}
            form.
          </p>

          <div className="space-y-3">
            {/* Field 1: Name → pastes into Claude's "Name" input */}
            <div>
              <p className="text-xs font-medium text-text-tertiary mb-1.5">
                1. Name{' '}
                <span className="text-text-secondary font-normal">
                  → Claude &quot;Name&quot;
                </span>
              </p>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(claudeConnectorName);
                  setCopiedClaudeName(true);
                  setTimeout(() => setCopiedClaudeName(false), 2000);
                }}
                className="w-full flex items-center justify-between p-3 rounded-xl bg-[#0d0d0d] border border-white/[0.06] hover:border-white/25 transition-colors group"
              >
                <code className="text-sm text-text-primary font-mono">
                  {claudeConnectorName}
                </code>
                {copiedClaudeName ? (
                  <Check className="w-4 h-4 text-green-400" />
                ) : (
                  <Copy className="w-4 h-4 text-text-quaternary group-hover:text-text-secondary transition-colors" />
                )}
              </button>
            </div>

            {/* Field 2: Server URL → pastes into Claude's "Remote MCP server URL" input */}
            <div>
              <p className="text-xs font-medium text-text-tertiary mb-1.5">
                2. Remote MCP server URL{' '}
                <span className="text-text-secondary font-normal">
                  → Claude &quot;Remote MCP server URL&quot;
                </span>
              </p>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(claudeConnectorUrl);
                  setCopiedClaudeUrl(true);
                  setTimeout(() => setCopiedClaudeUrl(false), 2000);
                }}
                className="w-full flex items-center justify-between p-3 rounded-xl bg-[#0d0d0d] border border-white/[0.06] hover:border-white/25 transition-colors group"
              >
                <code className="text-sm text-text-primary font-mono truncate mr-2">
                  {claudeConnectorUrl}
                </code>
                {copiedClaudeUrl ? (
                  <Check className="w-4 h-4 text-green-400 flex-shrink-0" />
                ) : (
                  <Copy className="w-4 h-4 text-text-quaternary group-hover:text-text-secondary transition-colors flex-shrink-0" />
                )}
              </button>
            </div>

            {/* Field 3: OAuth Client ID → pastes into Claude's Advanced "OAuth Client ID" */}
            <div>
              <p className="text-xs font-medium text-text-tertiary mb-1.5">
                3. OAuth Client ID{' '}
                <span className="text-text-secondary font-normal">
                  → Claude Advanced &quot;OAuth Client ID&quot;
                </span>
              </p>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(claudeConnectorClientId);
                  setCopiedClaudeClientId(true);
                  setTimeout(() => setCopiedClaudeClientId(false), 2000);
                }}
                className="w-full flex items-center justify-between p-3 rounded-xl bg-[#0d0d0d] border border-white/[0.06] hover:border-white/25 transition-colors group"
              >
                <code className="text-sm text-text-primary font-mono">
                  {claudeConnectorClientId}
                </code>
                {copiedClaudeClientId ? (
                  <Check className="w-4 h-4 text-green-400" />
                ) : (
                  <Copy className="w-4 h-4 text-text-quaternary group-hover:text-text-secondary transition-colors" />
                )}
              </button>
            </div>

            {/* Field 4: OAuth Client Secret → pastes into Claude's Advanced "OAuth Client Secret" */}
            <div>
              <p className="text-xs font-medium text-text-tertiary mb-1.5">
                4. OAuth Client Secret{' '}
                <span className="text-text-secondary font-normal">
                  → Claude Advanced &quot;OAuth Client Secret&quot;
                </span>
              </p>
              {claudeConnectorSecret ? (
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(claudeConnectorSecret);
                    setCopiedClaudeSecret(true);
                    setTimeout(() => setCopiedClaudeSecret(false), 2000);
                  }}
                  className="w-full flex items-center justify-between p-3 rounded-xl bg-[#0d0d0d] border border-white/[0.06] hover:border-white/25 transition-colors group"
                >
                  <code className="text-sm text-text-primary font-mono truncate mr-2">
                    {claudeConnectorSecret.slice(0, 8)}…{claudeConnectorSecret.slice(-4)}
                  </code>
                  {copiedClaudeSecret ? (
                    <Check className="w-4 h-4 text-green-400 flex-shrink-0" />
                  ) : (
                    <Copy className="w-4 h-4 text-text-quaternary group-hover:text-text-secondary transition-colors flex-shrink-0" />
                  )}
                </button>
              ) : (
                <div className="w-full flex items-center justify-between p-3 rounded-xl bg-[#0d0d0d] border border-white/[0.06] opacity-60">
                  <span className="text-sm text-text-quaternary italic">Leave blank</span>
                </div>
              )}
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-white/[0.06]">
            <ol className="text-xs text-text-tertiary space-y-1.5 list-decimal list-inside">
              <li>
                Open{' '}
                <span className="text-text-secondary">
                  claude.ai → Settings → Connectors → Add custom connector
                </span>
              </li>
              <li>
                Click each <span className="text-text-secondary">Copy</span> button above
                and paste into the matching field
              </li>
              <li>
                Under <span className="text-text-secondary">Advanced settings</span>,
                paste OAuth Client ID + Secret
              </li>
              <li>
                Click <span className="text-text-secondary">Add</span>, then{' '}
                <span className="text-text-secondary">Connect</span>
              </li>
            </ol>
          </div>
        </Card>
      </div>

      {/* Webhooks */}
      <div id="webhooks" className="space-y-3 scroll-mt-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider">
            Webhooks
          </h3>
          <a
            href="https://docs.omi.me/doc/developer/apps/Introduction"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-text-secondary hover:text-text-secondary transition-colors"
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
                  {index > 0 && <div className="border-t border-white/[0.06] my-4" />}
                  <div className="py-2">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-bg-tertiary">
                          <Icon className="w-4 h-4 text-text-tertiary" />
                        </div>
                        <div>
                          <p className="text-text-primary font-medium text-sm">
                            {webhook.label}
                          </p>
                          <p className="text-xs text-text-tertiary">
                            {webhook.description}
                          </p>
                        </div>
                      </div>
                      <Toggle
                        enabled={isEnabled}
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
                          className="w-full px-3 py-2 rounded-lg bg-bg-tertiary border border-white/[0.06] text-text-primary text-sm placeholder:text-text-quaternary focus:outline-none focus:border-white/25"
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
                            className="w-full px-3 py-2 rounded-lg bg-bg-tertiary border border-white/[0.06] text-text-primary text-sm placeholder:text-text-quaternary focus:outline-none focus:border-white/25"
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
      <div id="data-management" className="space-y-3 scroll-mt-4">
        <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider">
          Data Management
        </h3>
        <Card>
          <button
            onClick={onExportData}
            disabled={isExporting}
            className={cn(
              'w-full flex items-center gap-4 py-3 transition-colors',
              isExporting
                ? 'text-text-tertiary cursor-not-allowed'
                : 'text-text-primary hover:text-text-secondary',
            )}
          >
            <div className="p-2 rounded-lg bg-bg-tertiary">
              {isExporting ? (
                <Loader2 className="w-5 h-5 text-text-tertiary animate-spin" />
              ) : (
                <Download className="w-5 h-5 text-text-tertiary" />
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
            {!isExporting && <ExternalLink className="w-4 h-4 text-text-quaternary" />}
          </button>
        </Card>
        <Card className="border-red-500/20">
          <button
            onClick={() => setShowDeleteGraphDialog(true)}
            className="w-full flex items-center gap-4 py-3 text-text-primary hover:text-red-400 transition-colors"
          >
            <div className="p-2 rounded-lg bg-red-500/10">
              <Network className="w-5 h-5 text-red-400" />
            </div>
            <div className="flex-1 text-left">
              <p className="font-medium">Delete Knowledge Graph</p>
              <p className="text-xs text-text-tertiary">
                Clear all nodes and connections
              </p>
            </div>
            <Trash2 className="w-4 h-4 text-text-quaternary" />
          </button>
        </Card>
      </div>

      {/* Experimental Features */}
      <div id="experimental" className="space-y-3 scroll-mt-4">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-text-tertiary uppercase tracking-wider">
            Experimental
          </h3>
          <FlaskConical className="w-4 h-4 text-text-secondary" />
        </div>
        <Card>
          <div className="space-y-1">
            {/* Transcription Diagnostics */}
            <div className="flex items-center justify-between py-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-bg-tertiary">
                  <Activity className="w-4 h-4 text-text-tertiary" />
                </div>
                <div>
                  <p className="text-text-primary font-medium text-sm">
                    Transcription Diagnostics
                  </p>
                  <p className="text-xs text-text-tertiary">
                    Detailed diagnostic messages
                  </p>
                </div>
              </div>
              <Toggle
                enabled={experimentalFeatures.transcriptionDiagnostics}
                onChange={(v) => updateExperimentalFeature('transcriptionDiagnostics', v)}
              />
            </div>

            {/* Auto-create Speakers */}
            <div className="flex items-center justify-between py-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-bg-tertiary">
                  <UserPlus className="w-4 h-4 text-text-tertiary" />
                </div>
                <div>
                  <p className="text-text-primary font-medium text-sm">
                    Auto-create Speakers
                  </p>
                  <p className="text-xs text-text-tertiary">
                    Auto-create when name detected
                  </p>
                </div>
              </div>
              <Toggle
                enabled={experimentalFeatures.autoCreateSpeakers}
                onChange={(v) => updateExperimentalFeature('autoCreateSpeakers', v)}
              />
            </div>

            {/* Follow-up Questions */}
            <div className="flex items-center justify-between py-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-bg-tertiary">
                  <Lightbulb className="w-4 h-4 text-text-tertiary" />
                </div>
                <div>
                  <p className="text-text-primary font-medium text-sm">
                    Follow-up Questions
                  </p>
                  <p className="text-xs text-text-tertiary">
                    Suggest questions after conversations
                  </p>
                </div>
              </div>
              <Toggle
                enabled={experimentalFeatures.followUpQuestions}
                onChange={(v) => updateExperimentalFeature('followUpQuestions', v)}
              />
            </div>

            {/* Goal Tracker */}
            <div className="flex items-center justify-between py-3 border-b border-white/[0.06]">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-bg-tertiary">
                  <Target className="w-4 h-4 text-text-tertiary" />
                </div>
                <div>
                  <p className="text-text-primary font-medium text-sm">Goal Tracker</p>
                  <p className="text-xs text-text-tertiary">
                    Track your personal goals on homepage
                  </p>
                </div>
              </div>
              <Toggle
                enabled={experimentalFeatures.goalTracker}
                onChange={(v) => updateExperimentalFeature('goalTracker', v)}
              />
            </div>
          </div>
        </Card>
      </div>

      {/* Links */}
      <Card>
        <a
          href="https://docs.omi.me"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-between py-3 text-text-primary hover:text-text-secondary transition-colors"
        >
          <div className="flex items-center gap-3">
            <BookOpen className="w-5 h-5 text-text-tertiary" />
            <span>API Documentation</span>
          </div>
          <ExternalLink className="w-4 h-4" />
        </a>
      </Card>

      {/* Dialogs */}
      <CreateApiKeyDialog
        isOpen={showApiKeyDialog}
        onClose={() => setShowApiKeyDialog(false)}
        onCreateKey={onCreateApiKey}
      />
      <CreateMcpKeyDialog
        isOpen={showMcpKeyDialog}
        onClose={() => setShowMcpKeyDialog(false)}
        onCreateKey={onCreateMcpKey}
      />

      {/* Delete Knowledge Graph Dialog */}
      {showDeleteGraphDialog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          onClick={() => setShowDeleteGraphDialog(false)}
        >
          <div
            className="bg-bg-secondary rounded-2xl w-full max-w-md mx-4 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="p-3 rounded-xl bg-red-500/20">
                <AlertTriangle className="w-6 h-6 text-red-400" />
              </div>
              <h3 className="text-lg font-semibold text-text-primary">
                Delete Knowledge Graph?
              </h3>
            </div>
            <p className="text-text-secondary text-sm mb-6">
              This will delete all derived knowledge graph data (nodes and connections).
              Your original memories will remain safe. The graph will be rebuilt over
              time.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowDeleteGraphDialog(false)}
                className="flex-1 py-3 rounded-xl bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  onDeleteKnowledgeGraph();
                  setShowDeleteGraphDialog(false);
                }}
                className="flex-1 py-3 rounded-xl bg-red-500 text-white hover:bg-red-600 transition-colors"
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
