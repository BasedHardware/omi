import { notFound } from 'next/navigation';
import { cn } from '@/src/lib/utils';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me';
const SUPPORT_EMAIL = 'team@basedhardware.com';
const FETCH_TIMEOUT_MS = 10_000;

const STAGE_META: Record<string, { label: string; dot: string; text: string; bg: string }> = {
  none: { label: 'Normal', dot: 'bg-green-400', text: 'text-green-400', bg: 'bg-green-500/[0.06]' },
  warning: { label: 'Warning', dot: 'bg-amber-400', text: 'text-amber-400', bg: 'bg-amber-500/[0.06]' },
  throttle: { label: 'Throttled', dot: 'bg-orange-400', text: 'text-orange-400', bg: 'bg-orange-500/[0.06]' },
  restrict: { label: 'Restricted', dot: 'bg-red-400', text: 'text-red-400', bg: 'bg-red-500/[0.06]' },
};

interface CaseStatus {
  case_ref: string;
  stage: 'none' | 'warning' | 'throttle' | 'restrict';
  message: string;
  created_at: string;
  updated_at: string;
  support_email?: string;
}

type CaseResult =
  | { kind: 'ok'; data: CaseStatus }
  | { kind: 'not_found' }
  | { kind: 'error' };

const EMAIL_RE = /^[a-zA-Z0-9.!#$&'*+/=^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$/;

function safeEmail(raw?: string): string {
  return raw && EMAIL_RE.test(raw) ? raw : SUPPORT_EMAIL;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function daysSince(iso: string): number {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 0;
  return Math.floor((Date.now() - d.getTime()) / (1000 * 60 * 60 * 24));
}

async function getCaseStatus(ref: string): Promise<CaseResult> {
  try {
    const res = await fetch(`${API_BASE_URL}/v1/fair-use/case/${encodeURIComponent(ref)}/status`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (res.status === 404) return { kind: 'not_found' };
    if (!res.ok) return { kind: 'error' };
    return { kind: 'ok', data: await res.json() };
  } catch {
    return { kind: 'error' };
  }
}

export default async function CaseStatusPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;

  if (!/^FU-[A-Fa-f0-9]{6,12}$/i.test(ref)) {
    notFound();
  }

  const result = await getCaseStatus(ref);

  if (result.kind === 'not_found') {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
        <div className="max-w-md w-full text-center">
          <h1 className="text-lg font-semibold text-white mb-2">Case Not Found</h1>
          <p className="text-sm text-zinc-400 mb-1">
            No case found for reference <span className="font-mono text-zinc-300">{ref}</span>
          </p>
          <p className="text-xs text-zinc-500 mt-4">
            If you believe this is an error, contact{' '}
            <a href={`mailto:${SUPPORT_EMAIL}`} className="text-purple-400 hover:text-purple-300">
              {SUPPORT_EMAIL}
            </a>
          </p>
        </div>
      </div>
    );
  }

  if (result.kind === 'error') {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
        <div className="max-w-md w-full text-center">
          <h1 className="text-lg font-semibold text-white mb-2">Something Went Wrong</h1>
          <p className="text-sm text-zinc-400 mb-1">
            Unable to load case <span className="font-mono text-zinc-300">{ref}</span> right now.
          </p>
          <p className="text-xs text-zinc-500 mt-4">Please try again later or contact{' '}
            <a href={`mailto:${SUPPORT_EMAIL}`} className="text-purple-400 hover:text-purple-300">
              {SUPPORT_EMAIL}
            </a>
          </p>
        </div>
      </div>
    );
  }

  const status = result.data;
  const email = safeEmail(status.support_email);
  const meta = STAGE_META[status.stage] ?? STAGE_META['none'];
  const updatedDays = daysSince(status.updated_at);

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center p-6">
      <div className="max-w-md w-full space-y-5">
        <div className="text-center">
          <h1 className="text-lg font-semibold text-white">Case Status</h1>
          <p className="text-xs text-zinc-500 font-mono mt-1">{status.case_ref}</p>
        </div>

        <div
          className={cn(
            'rounded-2xl p-5',
            'bg-gradient-to-b from-white/[0.03] to-white/[0.01]',
            'shadow-[0_0_0_1px_rgba(255,255,255,0.04),0_2px_4px_rgba(0,0,0,0.1),0_8px_16px_rgba(0,0,0,0.1)]'
          )}
        >
          <div className={cn('flex items-center gap-2.5 px-3 py-2 rounded-xl mb-4', meta.bg)}>
            <div className={cn('w-2 h-2 rounded-full', meta.dot)} />
            <span className={cn('text-sm font-medium', meta.text)}>{meta.label}</span>
          </div>

          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-xs text-zinc-500">Created</span>
              <span className="text-sm text-zinc-300">{formatDate(status.created_at)}</span>
            </div>
            <div className="h-px bg-zinc-800" />
            <div className="flex justify-between items-center">
              <span className="text-xs text-zinc-500">Last Updated</span>
              <span className="text-sm text-zinc-300">{formatDate(status.updated_at)}</span>
            </div>
          </div>

          {status.message && (
            <>
              <div className="h-px bg-zinc-800 my-3" />
              <p className="text-sm text-zinc-400 leading-relaxed">{status.message}</p>
            </>
          )}
        </div>

        {updatedDays >= 3 && (
          <div className="rounded-xl bg-zinc-900/50 px-4 py-3">
            <p className="text-xs text-zinc-400 leading-relaxed">
              This case hasn&apos;t been updated in {updatedDays} days. If you need assistance, please contact{' '}
              <a href={`mailto:${email}`} className="text-purple-400 hover:text-purple-300">
                {email}
              </a>
            </p>
          </div>
        )}

        <p className="text-center text-xs text-zinc-600">
          Need help?{' '}
          <a href={`mailto:${email}`} className="text-purple-400/70 hover:text-purple-300">
            {email}
          </a>
        </p>
      </div>
    </div>
  );
}
