'use client';

import { useCallback, useEffect, useState } from 'react';
import { KeyRound, RefreshCw, Trash2, TriangleAlert } from 'lucide-react';
import { Button } from '@/src/components/ui/button';
import { Input } from '@/src/components/ui/input';
import { Label } from '@/src/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/src/components/ui/dialog';
import {
  DEFAULT_MCP_SCOPES,
  MCP_SCOPES,
  createMcpKey,
  listMcpKeys,
  revokeMcpKey,
  rotateMcpKey,
  type McpApiKey,
  type McpApiKeyCreated,
  type McpScope,
} from '@/src/lib/api/mcp-keys';
import { useSessionToken } from '../hooks/use-session-token';
import CopyButton from './copy-button';

function formatTimestamp(value?: string | null) {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function KeysManager() {
  const { user, loading, getToken } = useSessionToken();
  const [keys, setKeys] = useState<McpApiKey[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [scopes, setScopes] = useState<McpScope[]>(DEFAULT_MCP_SCOPES);
  // Held in component state only, for the lifetime of this dialog. Never written
  // to durable browser storage or a public env var — see the surface tripwires.
  const [revealed, setRevealed] = useState<McpApiKeyCreated | null>(null);
  const [revealSource, setRevealSource] = useState<'created' | 'rotated'>('created');

  const refresh = useCallback(async () => {
    const token = await getToken();
    if (!token) return;
    try {
      setKeys(await listMcpKeys(token));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load keys.');
    }
  }, [getToken]);

  useEffect(() => {
    if (!loading && user) void refresh();
  }, [loading, user, refresh]);

  const toggleScope = (scope: McpScope) => {
    setScopes((current) =>
      current.includes(scope) ? current.filter((s) => s !== scope) : [...current, scope],
    );
  };

  const submitCreate = async () => {
    const token = await getToken();
    if (!token || !name.trim()) return;
    setBusy(true);
    try {
      const created = await createMcpKey(token, name.trim(), scopes);
      setRevealSource('created');
      setRevealed(created);
      setCreateOpen(false);
      setName('');
      setScopes(DEFAULT_MCP_SCOPES);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the key.');
    } finally {
      setBusy(false);
    }
  };

  const rotate = async (keyId: string) => {
    const token = await getToken();
    if (!token) return;
    setBusy(true);
    try {
      const rotated = await rotateMcpKey(token, keyId);
      setRevealSource('rotated');
      setRevealed(rotated);
      await refresh();
    } catch (err) {
      setError(
        err instanceof Error
          ? `Rotation failed: ${err.message}`
          : 'Could not rotate the key.',
      );
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (keyId: string) => {
    const token = await getToken();
    if (!token) return;
    setBusy(true);
    try {
      await revokeMcpKey(token, keyId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not revoke the key.');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-neutral-500">Checking your session…</p>;
  }

  if (!user) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-8 text-center">
        <KeyRound className="mx-auto h-5 w-5 text-neutral-500" aria-hidden="true" />
        <p className="mt-3 text-sm text-neutral-300">
          Sign in to Omi to manage MCP keys.
        </p>
        <p className="mt-1 text-xs text-neutral-500">
          Keys are issued against your Omi session and are scoped to your account.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => setCreateOpen(true)} disabled={busy}>
          Create key
        </Button>
        <Button variant="outline" onClick={() => void refresh()} disabled={busy}>
          Refresh
        </Button>
        {error ? <span className="text-xs text-[#ff806a]">{error}</span> : null}
      </div>

      <div className="overflow-hidden rounded-xl border border-white/10">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-white/10 bg-white/[0.02] text-[11px] uppercase tracking-[0.14em] text-neutral-500">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Prefix</th>
              <th className="px-4 py-3 font-medium">Scopes</th>
              <th className="px-4 py-3 font-medium">Created</th>
              <th className="px-4 py-3 font-medium">Last used</th>
              <th className="px-4 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => (
              <tr key={key.id} className="border-b border-white/5 last:border-b-0">
                <td className="px-4 py-3 text-neutral-200">{key.name}</td>
                <td className="px-4 py-3 font-mono text-xs text-neutral-400">
                  {key.key_prefix ?? '—'}
                  <span className="text-neutral-600">…</span>
                </td>
                <td className="px-4 py-3 font-mono text-[11px] text-neutral-400">
                  {(key.scopes ?? DEFAULT_MCP_SCOPES).join(' ')}
                </td>
                <td className="px-4 py-3 text-xs text-neutral-400">
                  {formatTimestamp(key.created_at)}
                </td>
                <td className="px-4 py-3 text-xs text-neutral-400">
                  {formatTimestamp(key.last_used_at)}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => void rotate(key.id)}
                      disabled={busy}
                      className="inline-flex items-center gap-1.5 rounded-md border border-white/10 px-2.5 py-1 text-xs text-neutral-300 transition-colors hover:border-white/25 hover:text-white disabled:opacity-40"
                    >
                      <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                      Rotate
                    </button>
                    <button
                      type="button"
                      onClick={() => void revoke(key.id)}
                      disabled={busy}
                      className="inline-flex items-center gap-1.5 rounded-md border border-white/10 px-2.5 py-1 text-xs text-[#ff806a] transition-colors hover:border-[#ff806a]/40 disabled:opacity-40"
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                      Revoke
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {keys.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="px-4 py-10 text-center text-sm text-neutral-500"
                >
                  No MCP keys yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="dark border-white/10 bg-[#0d0d0d] text-neutral-100">
          <DialogHeader>
            <DialogTitle>Create MCP key</DialogTitle>
            <DialogDescription className="text-neutral-400">
              The raw key is shown once, immediately after creation.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="mcp-key-name">Name</Label>
              <Input
                id="mcp-key-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Claude Desktop"
                className="border-white/10 bg-white/[0.03] text-neutral-100"
              />
            </div>
            <fieldset className="flex flex-col gap-2">
              <legend className="text-sm font-medium text-neutral-200">Scopes</legend>
              <div className="grid grid-cols-2 gap-1.5">
                {MCP_SCOPES.map((scope) => (
                  <label
                    key={scope}
                    className="flex cursor-pointer items-center gap-2 rounded-md border border-white/10 px-2.5 py-1.5 font-mono text-[11px] text-neutral-300"
                  >
                    <input
                      type="checkbox"
                      checked={scopes.includes(scope)}
                      onChange={() => toggleScope(scope)}
                      className="h-3.5 w-3.5 accent-[#b9f36b]"
                    />
                    {scope}
                  </label>
                ))}
              </div>
              <p className="text-xs text-neutral-500">
                Default is <code className="font-mono">memories.read</code>. Grant write
                scopes only when the integration writes.
              </p>
            </fieldset>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => void submitCreate()} disabled={busy || !name.trim()}>
              Create key
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={revealed !== null} onOpenChange={() => setRevealed(null)}>
        <DialogContent className="dark border-white/10 bg-[#0d0d0d] text-neutral-100">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <TriangleAlert className="h-4 w-4 text-[#ff806a]" aria-hidden="true" />
              {revealSource === 'rotated' ? 'Key rotated' : 'Key created'}
            </DialogTitle>
            <DialogDescription className="text-[#ff806a]">
              Copy it now. You will not see this key again.
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-lg border border-white/10 bg-black/60 p-3">
            <code className="block break-all font-mono text-[13px] leading-6 text-neutral-100">
              {revealed?.key}
            </code>
          </div>
          <DialogFooter className="items-center">
            <CopyButton value={revealed?.key ?? ''} label="Copy key" />
            <Button onClick={() => setRevealed(null)}>I saved it</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
