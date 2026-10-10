'use client';

import { useState } from 'react';
import { Check, Copy, KeyRound, Loader2, RefreshCw, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import type {
  WebhookSigningSecretIssuedResponse,
  WebhookSigningSecretStatusResponse,
} from '@/lib/omiApi.generated';

const DOCS_URL =
  'https://docs.omi.me/doc/developer/apps/Integrations#verifying-webhook-signatures';

/**
 * One row that manages a webhook signing secret: create, rotate, delete, and the
 * single moment the secret is visible. Shared by the per-user developer webhooks
 * (Settings > Developer) and the integration-app editor, which differ only in
 * which endpoints the callbacks hit.
 *
 * `status` is `null` while the parent is still loading it. Callbacks return `null`
 * / `false` on failure (the parent toasts if it wants to); the row shows an inline
 * error either way so a failed click is never silent.
 */
export function WebhookSigningSecretControl({
  status,
  loadError = false,
  onRetry,
  onIssue,
  onDelete,
}: {
  status: WebhookSigningSecretStatusResponse | null;
  loadError?: boolean;
  onRetry?: () => void;
  onIssue: () => Promise<WebhookSigningSecretIssuedResponse | null>;
  onDelete: () => Promise<boolean>;
}) {
  const [busy, setBusy] = useState<'issue' | 'delete' | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [issued, setIssued] = useState<{
    secret: string;
    rotated: boolean;
    previousValidUntil: string | null;
  } | null>(null);
  const [confirm, setConfirm] = useState<'rotate' | 'delete' | null>(null);

  const configured = status?.configured === true;
  const previousValidUntil = status?.previous_valid_until
    ? new Date(status.previous_valid_until)
    : null;
  const previousStillValid =
    previousValidUntil !== null && previousValidUntil > new Date();

  const issue = async () => {
    if (busy) return;
    setBusy('issue');
    setActionError(null);
    const wasConfigured = configured;
    const result = await onIssue();
    setBusy(null);
    if (!result) {
      setActionError(
        wasConfigured
          ? 'Could not rotate the secret. Try again.'
          : 'Could not create the secret. Try again.',
      );
      return;
    }
    setIssued({
      secret: result.secret,
      rotated: wasConfigured,
      previousValidUntil: result.previous_valid_until ?? null,
    });
  };

  const remove = async () => {
    if (busy) return;
    setBusy('delete');
    setActionError(null);
    const ok = await onDelete();
    setBusy(null);
    if (!ok) setActionError('Could not delete the secret. Try again.');
  };

  let statusText: string;
  if (loadError) {
    statusText = 'Could not load the signing status.';
  } else if (status === null) {
    statusText = 'Checking…';
  } else if (!configured) {
    statusText = 'Not set. Deliveries carry no signature.';
  } else {
    statusText = status.created_at
      ? `Signing since ${new Date(status.created_at).toLocaleDateString()}.`
      : 'Signing is on.';
    if (previousStillValid && previousValidUntil) {
      statusText += ` Previous secret valid until ${previousValidUntil.toLocaleString()}.`;
    }
  }

  const pill =
    'flex items-center gap-1.5 rounded-full bg-white/[0.08] px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-white/[0.14] disabled:cursor-not-allowed disabled:opacity-60';

  return (
    <div className="py-2">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="rounded-lg bg-bg-tertiary p-2">
            <KeyRound className="h-4 w-4 text-text-tertiary" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-text-primary">Signing secret</p>
            <p className="text-xs text-text-tertiary">
              {statusText}{' '}
              <a
                href={DOCS_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="underline decoration-white/20 underline-offset-2 hover:text-text-secondary"
              >
                How to verify
              </a>
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {loadError && onRetry ? (
            <button type="button" onClick={onRetry} className={pill}>
              Retry
            </button>
          ) : status === null ? (
            <Loader2
              className="h-4 w-4 animate-spin text-text-tertiary"
              aria-label="Loading signing status"
            />
          ) : configured ? (
            <>
              <button
                type="button"
                onClick={() => setConfirm('rotate')}
                disabled={busy !== null}
                className={pill}
              >
                {busy === 'issue' ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
                Rotate
              </button>
              <button
                type="button"
                onClick={() => setConfirm('delete')}
                disabled={busy !== null}
                aria-label="Delete signing secret"
                className="rounded-lg p-2 text-text-secondary transition-colors hover:bg-red-500/10 hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === 'delete' ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={issue}
              disabled={busy !== null}
              className={pill}
            >
              {busy === 'issue' ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <KeyRound className="h-3.5 w-3.5" />
              )}
              Create secret
            </button>
          )}
        </div>
      </div>
      {actionError && (
        <p role="alert" className="mt-2 text-xs text-red-400">
          {actionError}
        </p>
      )}

      <ConfirmDialog
        open={confirm === 'rotate'}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Rotate signing secret?"
        description="A new secret starts signing immediately. The current one keeps working for 24 hours so you can switch your server over. Only the last two secrets are kept."
        confirmLabel="Rotate"
        onConfirm={() => void issue()}
      />
      <ConfirmDialog
        open={confirm === 'delete'}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Delete signing secret?"
        description="Deliveries will no longer carry X-Omi-Signature. A receiver that requires the header will start rejecting them."
        confirmLabel="Delete"
        variant="danger"
        onConfirm={() => void remove()}
      />

      <SigningSecretDialog issued={issued} onClose={() => setIssued(null)} />
    </div>
  );
}

// The one moment the secret is readable; closing it clears the value from memory.
function SigningSecretDialog({
  issued,
  onClose,
}: {
  issued: { secret: string; rotated: boolean; previousValidUntil: string | null } | null;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);

  if (!issued) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(issued.secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be denied; the secret stays visible to select by hand.
    }
  };

  const handleClose = () => {
    setCopied(false);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={handleClose}
    >
      <div
        role="dialog"
        aria-labelledby="signing-secret-title"
        className="mx-4 w-full max-w-md overflow-hidden rounded-2xl bg-bg-secondary p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center gap-3">
          <div className="rounded-xl bg-green-500/20 p-3">
            <Check className="h-6 w-6 text-green-400" />
          </div>
          <div>
            <h3
              id="signing-secret-title"
              className="text-lg font-semibold text-text-primary"
            >
              {issued.rotated ? 'Signing secret rotated' : 'Signing secret created'}
            </h3>
            <p className="text-sm text-text-tertiary">
              Save it now - you won&apos;t see it again!
            </p>
          </div>
        </div>
        <div className="mb-4 rounded-xl bg-bg-tertiary p-4">
          <p className="mb-2 text-xs text-text-tertiary">Your signing secret</p>
          <code className="break-all font-mono text-sm text-text-primary">
            {issued.secret}
          </code>
        </div>
        {issued.rotated && issued.previousValidUntil && (
          <p className="mb-4 text-xs text-text-tertiary">
            Your previous secret keeps working until{' '}
            {new Date(issued.previousValidUntil).toLocaleString()}.
          </p>
        )}
        <div className="flex gap-3">
          <button
            type="button"
            onClick={handleCopy}
            className={cn(
              'flex flex-1 items-center justify-center gap-2 rounded-xl px-4 py-3 font-medium transition-colors',
              copied
                ? 'bg-green-500/20 text-green-400'
                : 'bg-text-primary text-bg-primary hover:bg-text-primary/90',
            )}
          >
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copied ? 'Copied!' : 'Copy secret'}
          </button>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-xl bg-bg-tertiary px-4 py-3 text-text-secondary transition-colors hover:bg-bg-quaternary"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
