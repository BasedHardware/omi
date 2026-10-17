'use client';

import { useState } from 'react';
import { AlertTriangle, Check, Loader2, Lock } from 'lucide-react';
import type { AgentSecretSource } from '@/lib/agentPrompts';
import { createZkrShare, type ZkrShare } from '@/lib/zkr';
import { CopyButton, PromptPreview } from './PromptBlock';

/**
 * What a user sees right after creating a key: the way to hand it to an agent
 * without pasting it anywhere. "Send to My Agent Securely" encrypts the key in
 * the browser into a one-time zkr link and builds the prompt around that link;
 * the raw key stays behind a deliberate, warned fallback.
 */
export function KeyHandoff({
  secret,
  keyLabel,
  buildPrompt,
  onDone,
  createShare = createZkrShare,
}: {
  secret: string;
  keyLabel: string;
  buildPrompt: (source: AgentSecretSource) => string;
  onDone: () => void;
  /** Injected in tests and renders; production uses the zkr relay. */
  createShare?: (secret: string) => Promise<ZkrShare>;
}) {
  const [share, setShare] = useState<ZkrShare | null>(null);
  const [status, setStatus] = useState<'idle' | 'sending' | 'error'>('idle');
  const [showKey, setShowKey] = useState(false);

  const send = async () => {
    setStatus('sending');
    try {
      setShare(await createShare(secret));
      setStatus('idle');
    } catch {
      setStatus('error');
    }
  };

  const prompt = share ? buildPrompt({ kind: 'zkr', agentLink: share.agentLink }) : null;

  return (
    <div className="p-6">
      <div className="mb-5 flex items-center gap-3">
        <div className="rounded-xl bg-green-500/20 p-3">
          <Check className="h-6 w-6 text-green-400" />
        </div>
        <div>
          <h3 className="text-lg font-semibold text-text-primary">{keyLabel} Created</h3>
          <p className="text-sm text-text-tertiary">
            This is the only time the full key is available.
          </p>
        </div>
      </div>

      {prompt ? (
        <div className="space-y-3">
          <p className="text-sm text-text-secondary">
            Paste this prompt into your agent. The link inside opens once and expires in 1
            hour; the key itself is not in the prompt.
          </p>
          <PromptPreview prompt={prompt} label="Agent prompt with secure link" />
          <CopyButton text={prompt} label="Copy Prompt" className="w-full" />
        </div>
      ) : (
        <div className="space-y-3 rounded-xl bg-bg-tertiary p-4">
          <div className="flex items-start gap-3">
            <Lock className="mt-0.5 h-4 w-4 flex-shrink-0 text-text-tertiary" />
            <p className="text-sm text-text-secondary">
              Omi encrypts the key in your browser and turns it into a one-time link that
              expires in 1 hour. Your agent opens it with{' '}
              <code className="font-mono text-xs text-text-primary">zkr</code>, so the key
              never appears in your chat.
            </p>
          </div>
          <button
            type="button"
            onClick={send}
            disabled={status === 'sending'}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-text-primary px-4 py-3 font-medium text-bg-primary transition-colors hover:bg-text-primary/90 disabled:opacity-70"
          >
            {status === 'sending' && <Loader2 className="h-4 w-4 animate-spin" />}
            {status === 'sending' ? 'Encrypting…' : 'Send to My Agent Securely'}
          </button>
          {status === 'error' && (
            <p role="alert" className="text-xs text-red-400">
              Couldn&apos;t create the secure link. Try again, or copy the key below.
            </p>
          )}
        </div>
      )}

      <div className="mt-4 border-t border-white/[0.06] pt-4">
        {showKey ? (
          <div className="space-y-3">
            <div className="flex items-start gap-2 rounded-xl bg-yellow-500/10 p-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-yellow-400" />
              <p className="text-xs text-yellow-400">
                Anyone with this key can read your Omi data. Store it in a secret manager
                — pasting it into a chat leaves it in that chat&apos;s history.
              </p>
            </div>
            <div className="rounded-xl bg-bg-tertiary p-4">
              <p className="mb-2 text-xs text-text-tertiary">Your {keyLabel}</p>
              <code className="break-all font-mono text-sm text-text-primary">
                {secret}
              </code>
            </div>
            <CopyButton
              text={secret}
              label="Copy Key"
              variant="secondary"
              className="w-full"
            />
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setShowKey(true)}
            className="text-xs text-text-tertiary underline-offset-2 transition-colors hover:text-text-primary hover:underline"
          >
            Show the key instead
          </button>
        )}
      </div>

      <button
        type="button"
        onClick={onDone}
        className="mt-5 w-full rounded-xl bg-bg-tertiary px-4 py-3 text-text-secondary transition-colors hover:bg-bg-quaternary"
      >
        Done
      </button>
    </div>
  );
}
