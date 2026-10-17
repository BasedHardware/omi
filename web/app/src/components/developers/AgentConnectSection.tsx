'use client';

import { useState } from 'react';
import { Code, KeyRound, ShieldCheck, Sparkles } from 'lucide-react';
import { Card } from '@/components/settings/SettingsCard';
import { CreateApiKeyDialog } from '@/components/settings/DeveloperSection';
import { CreateMcpKeyDialog } from '@/components/settings/McpSection';
import {
  buildDevApiPrompt,
  buildMcpKeyPrompt,
  buildMcpOauthPrompt,
} from '@/lib/agentPrompts';
import { hostedMcpUrl } from '@/lib/mcpConfig';
import type { DeveloperApiKey, McpApiKey } from '@/types/user';
import { CopyButton, PromptPreview } from './PromptBlock';

function PathCard({
  id,
  icon: Icon,
  title,
  badge,
  description,
  prompt,
  promptLabel,
  action,
}: {
  id: string;
  icon: typeof Code;
  title: string;
  badge: string;
  description: React.ReactNode;
  prompt: string;
  promptLabel: string;
  action: React.ReactNode;
}) {
  return (
    <Card>
      <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-4 space-y-4">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-bg-tertiary p-2">
            <Icon className="h-5 w-5 text-text-tertiary" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 id={`${id}-title`} className="font-medium text-text-primary">
                {title}
              </h3>
              <span className="rounded-full bg-white/[0.08] px-2 py-0.5 text-[11px] font-medium text-text-secondary">
                {badge}
              </span>
            </div>
            <p className="mt-1 text-sm text-text-tertiary">{description}</p>
          </div>
        </div>
        <PromptPreview prompt={prompt} label={promptLabel} />
        <div className="flex flex-col gap-2 sm:flex-row">{action}</div>
      </section>
    </Card>
  );
}

/**
 * The lead of the Developers page: three ways to connect an agent, each with
 * a prompt the user pastes into any agent so it can set itself up. The key
 * paths create the key here and hand it over through a one-time zkr link.
 */
export function AgentConnectSection({
  apiBase,
  onCreateApiKey,
  onCreateMcpKey,
}: {
  apiBase: string;
  onCreateApiKey: (name: string, scopes: string[]) => Promise<DeveloperApiKey | null>;
  onCreateMcpKey: (name: string) => Promise<McpApiKey | null>;
}) {
  const [dialog, setDialog] = useState<'mcp' | 'api' | null>(null);
  const pending = { kind: 'pending' } as const;
  const mcpUrl = hostedMcpUrl(apiBase);

  return (
    <div id="connect" className="scroll-mt-4 space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-text-primary">Connect an agent</h2>
        <p className="mt-1 max-w-2xl text-sm text-text-secondary">
          Give Claude, ChatGPT, Codex, Cursor, OpenClaw, or any other agent access to your
          Omi memories, conversations, and tasks. Pick a path, copy its prompt, and paste
          it into your agent — it does the setup.
        </p>
      </div>

      <PathCard
        id="connect-oauth"
        icon={ShieldCheck}
        title="MCP with sign-in"
        badge="Recommended"
        description={
          <>
            For agents that support remote MCP with OAuth. You approve access in your
            browser; no key is created or shared. Server:{' '}
            <code className="break-all font-mono text-xs text-text-secondary">
              {mcpUrl}
            </code>
          </>
        }
        prompt={buildMcpOauthPrompt(apiBase)}
        promptLabel="MCP sign-in prompt"
        action={<CopyButton text={buildMcpOauthPrompt(apiBase)} label="Copy Prompt" />}
      />

      <PathCard
        id="connect-mcp-key"
        icon={KeyRound}
        title="MCP with an API key"
        badge="Creates a key"
        description="For MCP clients that take a bearer header instead of OAuth. Omi creates an MCP key and sends it to your agent through a one-time encrypted link."
        prompt={buildMcpKeyPrompt(apiBase, pending)}
        promptLabel="MCP API key prompt preview"
        action={
          <button
            type="button"
            onClick={() => setDialog('mcp')}
            className="flex items-center justify-center gap-2 rounded-xl bg-text-primary px-4 py-2.5 text-sm font-medium text-bg-primary transition-colors hover:bg-text-primary/90"
          >
            <Sparkles className="h-4 w-4" />
            Create MCP Key & Prompt
          </button>
        }
      />

      <PathCard
        id="connect-dev-api"
        icon={Code}
        title="Developer API"
        badge="Creates a key"
        description="For scripts and agents that call REST endpoints directly. Choose scopes, then send the key to your agent through a one-time encrypted link."
        prompt={buildDevApiPrompt(apiBase, pending)}
        promptLabel="Developer API prompt preview"
        action={
          <button
            type="button"
            onClick={() => setDialog('api')}
            className="flex items-center justify-center gap-2 rounded-xl bg-text-primary px-4 py-2.5 text-sm font-medium text-bg-primary transition-colors hover:bg-text-primary/90"
          >
            <Sparkles className="h-4 w-4" />
            Create API Key & Prompt
          </button>
        }
      />

      <CreateMcpKeyDialog
        isOpen={dialog === 'mcp'}
        onClose={() => setDialog(null)}
        onCreateKey={onCreateMcpKey}
      />
      <CreateApiKeyDialog
        isOpen={dialog === 'api'}
        onClose={() => setDialog(null)}
        onCreateKey={onCreateApiKey}
      />
    </div>
  );
}
