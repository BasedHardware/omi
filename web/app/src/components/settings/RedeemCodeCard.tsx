import { useState } from 'react';
import { Ticket } from 'lucide-react';
import { ApiHttpError, redeemCode } from '@/lib/api';
import { Card } from '@/components/settings/SettingsCard';
import type { RedeemCodeResponse } from '@/types/user';

function formatDay(seconds: number): string {
  return new Date(seconds * 1000).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

export function redeemedMessage(result: RedeemCodeResponse): string {
  const when = result.applies_at ? ` on ${formatDay(result.applies_at)}` : '';
  if (result.percent_off === 100) return `Code applied. You won't be charged${when}.`;
  if (result.percent_off)
    return `Code applied. ${result.percent_off}% off your payment${when}.`;
  return `Code applied to your next payment${when}.`;
}

export function redeemErrorMessage(error: unknown): string {
  const status = error instanceof ApiHttpError ? error.status : 0;
  if (status === 409)
    return 'This code has already been used, or your plan already has a discount.';
  if (status === 429) return 'Too many tries. Please wait an hour and try again.';
  if (status === 400) {
    return "This code can't be applied. Check the code, and start the plan it's for first.";
  }
  return 'Could not apply this code. Please try again.';
}

/** Shown once a subscription exists, so a code also works during a free trial. */
export function RedeemCodeCard({ onRedeemed }: { onRedeemed: () => void }) {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const trimmed = code.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      setMessage(redeemedMessage(await redeemCode(trimmed)));
      setCode('');
      onRedeemed();
    } catch (err) {
      setError(redeemErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <div className="mb-3 flex items-center gap-2">
        <Ticket className="h-4 w-4 text-text-secondary" />
        <h4 className="text-sm font-semibold text-text-primary">Redeem a code</h4>
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="OMI-XXXX-XXXX"
          aria-label="Code"
          autoCapitalize="characters"
          className="min-w-0 flex-1 rounded-xl border border-bg-quaternary bg-bg-tertiary px-3 py-2 text-sm text-text-primary placeholder:text-text-quaternary focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy || !code.trim()}
          className="rounded-xl bg-text-primary px-4 py-2 text-sm font-semibold text-bg-primary disabled:opacity-50"
        >
          {busy ? 'Applying…' : 'Apply'}
        </button>
      </form>
      {message && <p className="mt-2 text-sm text-text-secondary">{message}</p>}
      {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
    </Card>
  );
}
