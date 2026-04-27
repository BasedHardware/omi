'use client';

import { useEffect, useState, useTransition } from 'react';
import { useAuth } from '@/src/hooks/useAuth';
import { Button } from '@/src/components/ui/button';
import { Card } from '@/src/components/ui/card';
import { Input } from '@/src/components/ui/input';
import { Label } from '@/src/components/ui/label';
import {
  fetchSettingsSnapshot,
  saveBYOKKey,
  saveEuPrivacyMode,
  testBYOKConnection,
  type SettingsSnapshot,
} from '@/src/app/settings/actions';

type Provider = 'openai' | 'anthropic' | 'gemini' | 'deepgram' | 'regolo';

interface ProviderRow {
  id: Provider;
  label: string;
  subtitle: string;
}

const PROVIDER_ROWS: ProviderRow[] = [
  { id: 'openai', label: 'OpenAI API Key', subtitle: 'For GPT calls.' },
  { id: 'anthropic', label: 'Anthropic API Key', subtitle: 'For chat (Claude).' },
  {
    id: 'gemini',
    label: 'Gemini API Key',
    subtitle: 'For proactive AI (memory, tasks, insights, focus).',
  },
  { id: 'deepgram', label: 'Deepgram API Key', subtitle: 'For live transcription.' },
  {
    id: 'regolo',
    label: 'Regolo API Key',
    subtitle: 'For EU Privacy Mode (Italy-hosted, zero retention). Optional.',
  },
];

type ConnectionStatus =
  | { kind: 'idle' }
  | { kind: 'testing' }
  | { kind: 'ok' }
  | { kind: 'error'; message: string };

export default function SettingsPage() {
  const { user, loading, isAuthenticated, signIn } = useAuth();

  if (loading) {
    return <div className="mx-auto max-w-2xl p-8">Loading…</div>;
  }
  if (!isAuthenticated || !user) {
    return (
      <div className="mx-auto max-w-2xl p-8">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="mt-4 text-sm text-zinc-400">
          Sign in to manage your API keys and EU Privacy Mode preferences.
        </p>
        <Button className="mt-6" onClick={signIn}>
          Sign in with Google
        </Button>
      </div>
    );
  }

  return <SettingsContent uid={user.uid} />;
}

function SettingsContent({ uid }: { uid: string }) {
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null);
  const [keyDrafts, setKeyDrafts] = useState<Record<Provider, string>>({
    openai: '',
    anthropic: '',
    gemini: '',
    deepgram: '',
    regolo: '',
  });
  const [statuses, setStatuses] = useState<Record<Provider, ConnectionStatus>>({
    openai: { kind: 'idle' },
    anthropic: { kind: 'idle' },
    gemini: { kind: 'idle' },
    deepgram: { kind: 'idle' },
    regolo: { kind: 'idle' },
  });
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    fetchSettingsSnapshot(uid).then(setSnapshot).catch(() => setSnapshot(null));
  }, [uid]);

  const handleSaveKey = (provider: Provider) => {
    const draft = keyDrafts[provider];
    startTransition(async () => {
      const result = await saveBYOKKey(uid, provider, draft);
      if (result.ok) {
        setKeyDrafts((d) => ({ ...d, [provider]: '' }));
        const fresh = await fetchSettingsSnapshot(uid);
        setSnapshot(fresh);
      } else {
        setStatuses((s) => ({ ...s, [provider]: { kind: 'error', message: result.error } }));
      }
    });
  };

  const handleTestKey = (provider: Provider) => {
    const draft = keyDrafts[provider];
    setStatuses((s) => ({ ...s, [provider]: { kind: 'testing' } }));
    startTransition(async () => {
      const result = await testBYOKConnection(provider, draft);
      setStatuses((s) => ({
        ...s,
        [provider]: result.ok ? { kind: 'ok' } : { kind: 'error', message: result.error },
      }));
    });
  };

  const handleClearKey = (provider: Provider) => {
    startTransition(async () => {
      await saveBYOKKey(uid, provider, '');
      const fresh = await fetchSettingsSnapshot(uid);
      setSnapshot(fresh);
      setStatuses((s) => ({ ...s, [provider]: { kind: 'idle' } }));
    });
  };

  const handlePrivacyToggle = () => {
    if (!snapshot) return;
    const next = !snapshot.eu_privacy_mode;
    setSnapshot({ ...snapshot, eu_privacy_mode: next });
    startTransition(async () => {
      await saveEuPrivacyMode(uid, next);
    });
  };

  const isConfigured = (p: Provider) => snapshot?.configured_providers.includes(p) ?? false;

  return (
    <div className="mx-auto max-w-2xl space-y-8 p-8">
      <h1 className="text-2xl font-semibold">Settings</h1>

      {/* EU Privacy Mode */}
      <Card className="space-y-3 p-6">
        <div className="flex items-start gap-3">
          <div className="flex-1">
            <h2 className="text-lg font-medium">EU Privacy Mode</h2>
            <p className="mt-1 text-sm text-zinc-400">
              Route AI traffic through regolo.ai in Italy — GDPR-compliant, zero data retention.
              Requires a Regolo API key configured below. Vision features stay on Gemini; you'll
              see a banner per request that leaves the EU.
            </p>
          </div>
          <Button
            variant={snapshot?.eu_privacy_mode ? 'default' : 'outline'}
            onClick={handlePrivacyToggle}
            disabled={!snapshot || pending}
            aria-pressed={snapshot?.eu_privacy_mode}
          >
            {snapshot?.eu_privacy_mode ? 'On' : 'Off'}
          </Button>
        </div>
      </Card>

      {/* Developer API Keys */}
      <section className="space-y-4">
        <h2 className="text-lg font-medium">Developer API Keys</h2>
        <p className="text-sm text-zinc-400">
          Optional. Bring your own keys to use your own provider quotas. Keys are encrypted at rest
          (AES-GCM with a per-user-derived key) and never shown back to you.
        </p>

        {PROVIDER_ROWS.map((row) => (
          <Card key={row.id} className="space-y-3 p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <Label htmlFor={`key-${row.id}`} className="font-medium">
                  {row.label}
                </Label>
                <p className="mt-1 text-sm text-zinc-400">{row.subtitle}</p>
              </div>
              {isConfigured(row.id) && (
                <span className="text-xs uppercase tracking-wide text-emerald-500">
                  Configured
                </span>
              )}
            </div>
            <Input
              id={`key-${row.id}`}
              type="password"
              autoComplete="off"
              placeholder={isConfigured(row.id) ? '•••• key on file ••••' : 'Paste key…'}
              value={keyDrafts[row.id]}
              onChange={(e) =>
                setKeyDrafts((d) => ({ ...d, [row.id]: e.target.value }))
              }
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                onClick={() => handleSaveKey(row.id)}
                disabled={pending || keyDrafts[row.id].trim() === ''}
              >
                Save
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleTestKey(row.id)}
                disabled={pending || keyDrafts[row.id].trim() === ''}
              >
                Test connection
              </Button>
              {isConfigured(row.id) && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => handleClearKey(row.id)}
                  disabled={pending}
                >
                  Clear
                </Button>
              )}
              {statuses[row.id].kind === 'testing' && (
                <span className="text-xs text-zinc-400">Testing…</span>
              )}
              {statuses[row.id].kind === 'ok' && (
                <span className="text-xs text-emerald-500">✓ Connection OK</span>
              )}
              {statuses[row.id].kind === 'error' && (
                <span className="text-xs text-red-500">
                  ✗ {(statuses[row.id] as { kind: 'error'; message: string }).message}
                </span>
              )}
            </div>
          </Card>
        ))}
      </section>
    </div>
  );
}
