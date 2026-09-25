'use client';

import { useState } from 'react';
import { Check, Copy, Plus, Server, Terminal, Trash2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { hostedMcpConfigJson, hostedMcpUrl } from '@/lib/mcpConfig';
import { CLAUDE_CONNECTOR_OAUTH } from '@/lib/settingsSections';
import type { McpApiKey } from '@/types/user';
import { Card } from './SettingsCard';

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
                  MCP Key Created
                </h3>
                <p className="text-sm text-text-tertiary">
                  Save this key now - you won&apos;t see it again!
                </p>
              </div>
            </div>
            <div className="mb-4 rounded-xl bg-bg-tertiary p-4">
              <p className="mb-2 text-xs text-text-tertiary">Your MCP Key</p>
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
              <h3 className="text-lg font-semibold text-text-primary">Create MCP Key</h3>
              <button
                onClick={handleClose}
                className="rounded-lg p-2 transition-colors hover:bg-bg-tertiary"
              >
                <X className="h-5 w-5 text-text-tertiary" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                  Key Name
                </label>
                <input
                  type="text"
                  value={keyName}
                  onChange={(e) => setKeyName(e.target.value)}
                  placeholder="e.g., Claude Code"
                  className="w-full rounded-xl border border-white/[0.06] bg-bg-tertiary px-4 py-3 text-text-primary placeholder:text-text-quaternary focus:border-white/25 focus:outline-none"
                />
              </div>
              <button
                onClick={handleCreate}
                disabled={!keyName.trim() || isCreating}
                className={cn(
                  'w-full rounded-xl py-3 font-medium transition-colors',
                  keyName.trim() && !isCreating
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

export function McpSection({
  mcpKeys,
  onCreateMcpKey,
  onDeleteMcpKey,
}: {
  mcpKeys: McpApiKey[];
  onCreateMcpKey: (name: string) => Promise<McpApiKey | null>;
  onDeleteMcpKey: (keyId: string) => void;
}) {
  const [showMcpKeyDialog, setShowMcpKeyDialog] = useState(false);
  const [copiedConfig, setCopiedConfig] = useState(false);
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [copiedClaudeName, setCopiedClaudeName] = useState(false);
  const [copiedClaudeUrl, setCopiedClaudeUrl] = useState(false);
  const [copiedClaudeClientId, setCopiedClaudeClientId] = useState(false);
  const [copiedClaudeSecret, setCopiedClaudeSecret] = useState(false);

  const mcpServerUrl = hostedMcpUrl(
    process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me',
  );

  // Claude connector values — mirror the 4 fields in Claude's "Add custom connector" form
  const claudeConnectorName = 'Omi Memory';
  const claudeConnectorUrl = mcpServerUrl;
  const claudeConnectorClientId = CLAUDE_CONNECTOR_OAUTH.clientId;
  const claudeConnectorSecret: string = CLAUDE_CONNECTOR_OAUTH.clientSecret;

  const claudeCodeConfig = hostedMcpConfigJson(mcpServerUrl);

  const copyConfig = () => {
    navigator.clipboard.writeText(claudeCodeConfig);
    setCopiedConfig(true);
    setTimeout(() => setCopiedConfig(false), 2000);
  };

  const copyUrl = () => {
    navigator.clipboard.writeText(mcpServerUrl);
    setCopiedUrl(true);
    setTimeout(() => setCopiedUrl(false), 2000);
  };

  return (
    <div id="mcp" className="scroll-mt-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-text-tertiary">
            MCP
          </h3>
          <a
            href="https://docs.omi.me/doc/developer/MCP"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-text-secondary transition-colors hover:text-text-secondary"
          >
            Docs ↗
          </a>
        </div>
        <button
          onClick={() => setShowMcpKeyDialog(true)}
          className="flex items-center gap-1.5 rounded-full bg-white/[0.08] px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-white/[0.14]"
        >
          <Plus className="h-3 w-3" />
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
                className="flex items-center justify-between rounded-xl bg-bg-tertiary p-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-text-primary">
                      {key.name}
                    </span>
                    <code className="rounded bg-bg-quaternary px-2 py-0.5 font-mono text-xs text-text-tertiary">
                      {key.key_prefix}...
                    </code>
                  </div>
                  <p className="mt-1 text-xs text-text-quaternary">
                    Created {new Date(key.created_at).toLocaleDateString()}
                    {key.last_used_at &&
                      ` • Last used ${new Date(key.last_used_at).toLocaleDateString()}`}
                  </p>
                </div>
                <button
                  onClick={() => onDeleteMcpKey(key.id)}
                  className="rounded-lg p-2 text-text-secondary transition-colors hover:bg-red-500/10 hover:text-red-400"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="py-6 text-center text-sm text-text-quaternary">
            No MCP keys created yet
          </p>
        )}
      </Card>

      {/* Claude Code config (~/.claude.json) */}
      <Card>
        <div className="mb-4 flex items-center gap-3">
          <div className="rounded-lg bg-bg-tertiary p-2">
            <Terminal className="h-5 w-5 text-text-tertiary" />
          </div>
          <div>
            <p className="font-medium text-text-primary">Claude Code</p>
            <p className="text-xs text-text-tertiary">Add to ~/.claude.json</p>
          </div>
        </div>
        <div className="overflow-x-auto rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-4 font-mono text-xs">
          <pre className="whitespace-pre text-text-secondary">{claudeCodeConfig}</pre>
        </div>
        <button
          onClick={copyConfig}
          className={cn(
            'mt-3 flex w-full items-center justify-center gap-2 rounded-xl py-2.5 transition-colors',
            copiedConfig
              ? 'bg-green-500/20 text-green-400'
              : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary',
          )}
        >
          {copiedConfig ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          {copiedConfig ? 'Copied!' : 'Copy Config'}
        </button>
      </Card>

      {/* Generic MCP Server Info */}
      <Card>
        <div className="mb-4 flex items-center gap-3">
          <div className="rounded-lg bg-bg-tertiary p-2">
            <Server className="h-5 w-5 text-text-tertiary" />
          </div>
          <div>
            <p className="font-medium text-text-primary">MCP Server</p>
            <p className="text-xs text-text-tertiary">
              Connect ChatGPT, Codex, Claude, or any MCP client to your data
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
              Server URL
            </p>
            <button
              onClick={copyUrl}
              className="flex w-full items-center justify-between rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-3 transition-colors hover:border-white/25"
            >
              <code className="mr-2 truncate font-mono text-sm text-text-primary">
                {mcpServerUrl}
              </code>
              {copiedUrl ? (
                <Check className="h-4 w-4 flex-shrink-0 text-green-400" />
              ) : (
                <Copy className="h-4 w-4 flex-shrink-0 text-text-quaternary" />
              )}
            </button>
          </div>

          <div className="border-t border-white/[0.06] pt-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
              API Key Auth
            </p>
            <div className="flex items-center gap-4 text-sm">
              <span className="text-text-tertiary">Header</span>
              <code className="font-mono text-xs text-text-quaternary">
                Authorization: Bearer &lt;key&gt;
              </code>
            </div>
          </div>

          <div className="border-t border-white/[0.06] pt-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
              OAuth
            </p>
            <p className="mb-2 text-xs text-text-tertiary">
              On claude.ai, add a custom connector and paste the server URL. If Claude
              asks for an advanced OAuth Client ID, use the value below and leave the
              secret blank — never use your MCP API key as an OAuth secret.
            </p>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-4">
                <span className="w-24 text-text-tertiary">Client ID</span>
                <code className="font-mono text-text-primary">
                  {CLAUDE_CONNECTOR_OAUTH.clientId}
                </code>
              </div>
              <div className="flex items-center gap-4">
                <span className="w-24 text-text-tertiary">Client Secret</span>
                <span className="text-xs italic text-text-quaternary">Leave blank</span>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* Claude Desktop connector — 4 copy fields mirroring the "Add custom connector" form */}
      <Card>
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center overflow-hidden rounded-xl border border-orange-500/20 bg-gradient-to-br from-orange-500/20 to-orange-600/10">
            <span className="text-lg font-semibold text-orange-400">C</span>
          </div>
          <div>
            <p className="font-medium text-text-primary">Claude Desktop</p>
            <p className="text-xs text-text-tertiary">Live MCP or memory pack</p>
          </div>
        </div>

        <p className="mb-4 text-sm text-text-secondary">
          Connect over MCP so Claude reads your memories live, or copy a memory pack. Each
          field below maps to Claude&rsquo;s{' '}
          <span className="text-text-tertiary">
            Settings → Connectors → Add custom connector
          </span>{' '}
          form.
        </p>

        <div className="space-y-3">
          {/* Field 1: Name → pastes into Claude's "Name" input */}
          <div>
            <p className="mb-1.5 text-xs font-medium text-text-tertiary">
              1. Name{' '}
              <span className="font-normal text-text-secondary">
                → Claude &quot;Name&quot;
              </span>
            </p>
            <button
              onClick={() => {
                navigator.clipboard.writeText(claudeConnectorName);
                setCopiedClaudeName(true);
                setTimeout(() => setCopiedClaudeName(false), 2000);
              }}
              className="group flex w-full items-center justify-between rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-3 transition-colors hover:border-white/25"
            >
              <code className="font-mono text-sm text-text-primary">
                {claudeConnectorName}
              </code>
              {copiedClaudeName ? (
                <Check className="h-4 w-4 text-green-400" />
              ) : (
                <Copy className="h-4 w-4 text-text-quaternary transition-colors group-hover:text-text-secondary" />
              )}
            </button>
          </div>

          {/* Field 2: Server URL → pastes into Claude's "Remote MCP server URL" input */}
          <div>
            <p className="mb-1.5 text-xs font-medium text-text-tertiary">
              2. Remote MCP server URL{' '}
              <span className="font-normal text-text-secondary">
                → Claude &quot;Remote MCP server URL&quot;
              </span>
            </p>
            <button
              onClick={() => {
                navigator.clipboard.writeText(claudeConnectorUrl);
                setCopiedClaudeUrl(true);
                setTimeout(() => setCopiedClaudeUrl(false), 2000);
              }}
              className="group flex w-full items-center justify-between rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-3 transition-colors hover:border-white/25"
            >
              <code className="mr-2 truncate font-mono text-sm text-text-primary">
                {claudeConnectorUrl}
              </code>
              {copiedClaudeUrl ? (
                <Check className="h-4 w-4 flex-shrink-0 text-green-400" />
              ) : (
                <Copy className="h-4 w-4 flex-shrink-0 text-text-quaternary transition-colors group-hover:text-text-secondary" />
              )}
            </button>
          </div>

          {/* Field 3: OAuth Client ID → pastes into Claude's Advanced "OAuth Client ID" */}
          <div>
            <p className="mb-1.5 text-xs font-medium text-text-tertiary">
              3. OAuth Client ID{' '}
              <span className="font-normal text-text-secondary">
                → Claude Advanced &quot;OAuth Client ID&quot;
              </span>
            </p>
            <button
              onClick={() => {
                navigator.clipboard.writeText(claudeConnectorClientId);
                setCopiedClaudeClientId(true);
                setTimeout(() => setCopiedClaudeClientId(false), 2000);
              }}
              className="group flex w-full items-center justify-between rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-3 transition-colors hover:border-white/25"
            >
              <code className="font-mono text-sm text-text-primary">
                {claudeConnectorClientId}
              </code>
              {copiedClaudeClientId ? (
                <Check className="h-4 w-4 text-green-400" />
              ) : (
                <Copy className="h-4 w-4 flex-shrink-0 text-text-quaternary transition-colors group-hover:text-text-secondary" />
              )}
            </button>
          </div>

          {/* Field 4: OAuth Client Secret → pastes into Claude's Advanced "OAuth Client Secret" */}
          <div>
            <p className="mb-1.5 text-xs font-medium text-text-tertiary">
              4. OAuth Client Secret{' '}
              <span className="font-normal text-text-secondary">
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
                className="group flex w-full items-center justify-between rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-3 transition-colors hover:border-white/25"
              >
                <code className="mr-2 truncate font-mono text-sm text-text-primary">
                  {claudeConnectorSecret.slice(0, 8)}…{claudeConnectorSecret.slice(-4)}
                </code>
                {copiedClaudeSecret ? (
                  <Check className="h-4 w-4 flex-shrink-0 text-green-400" />
                ) : (
                  <Copy className="h-4 w-4 flex-shrink-0 text-text-quaternary transition-colors group-hover:text-text-secondary" />
                )}
              </button>
            ) : (
              <div className="flex w-full items-center justify-between rounded-xl border border-white/[0.06] bg-[#0d0d0d] p-3 opacity-60">
                <span className="text-sm italic text-text-quaternary">Leave blank</span>
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 border-t border-white/[0.06] pt-4">
          <ol className="list-inside list-decimal space-y-1.5 text-xs text-text-tertiary">
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
              Under <span className="text-text-secondary">Advanced settings</span>, paste
              OAuth Client ID + Secret
            </li>
            <li>
              Click <span className="text-text-secondary">Add</span>, then{' '}
              <span className="text-text-secondary">Connect</span>
            </li>
          </ol>
        </div>
      </Card>

      <CreateMcpKeyDialog
        isOpen={showMcpKeyDialog}
        onClose={() => setShowMcpKeyDialog(false)}
        onCreateKey={onCreateMcpKey}
      />
    </div>
  );
}
