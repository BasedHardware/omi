import { getIdToken } from './firebase';

export type ReferralEnvironment = 'dev' | 'prod';

export interface ReferralClaimResult {
  claimed: boolean;
  trial_days: number;
}

export function navigateToDesktopDownload(): void {
  window.location.assign('https://macos.omi.me');
}

export function parseReferralEnvironment(
  value: string | null,
): ReferralEnvironment | null {
  return value === 'dev' || value === 'prod' ? value : null;
}

export class ReferralClaimError extends Error {
  constructor(message: string, public readonly retryable: boolean) {
    super(message);
  }
}

export async function claimReferralTrial(
  code: string,
  environment: ReferralEnvironment,
  options: { deadlineMs?: number; isCurrent?: () => boolean } = {},
): Promise<ReferralClaimResult> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const current = () => !controller.signal.aborted && (options.isCurrent?.() ?? true);
  const operation = async (): Promise<ReferralClaimResult> => {
    if (!current()) throw new ReferralClaimError('Referral attempt cancelled', false);
    const token = await getIdToken();
    if (!current()) throw new ReferralClaimError('Referral attempt cancelled', false);
    // Claims only start for a signed-in account, and getIdToken also returns null when
    // Firebase cannot read the token right now. Keep that ambiguous failure manually
    // retryable; the caller's account fence still applies to every retry.
    if (!token) throw new ReferralClaimError('Sign-in token unavailable', true);
    const response = await fetch('/api/referrals/claim', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, environment }),
      signal: controller.signal,
    });
    if (!response.ok)
      throw new ReferralClaimError(
        'Referral claim failed',
        response.status === 429 || response.status >= 500,
      );
    const result: unknown = await response.json();
    if (
      typeof result !== 'object' ||
      result === null ||
      typeof (result as ReferralClaimResult).claimed !== 'boolean' ||
      !Number.isInteger((result as ReferralClaimResult).trial_days) ||
      (result as ReferralClaimResult).trial_days < 0
    ) {
      throw new ReferralClaimError('Invalid referral response', true);
    }
    return result as ReferralClaimResult;
  };
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      reject(new ReferralClaimError('Referral service timed out', true));
      controller.abort();
    }, options.deadlineMs ?? 15_000);
  });
  try {
    return await Promise.race([operation(), timeout]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}
