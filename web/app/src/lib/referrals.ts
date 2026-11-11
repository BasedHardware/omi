import type { User } from 'firebase/auth';
import { auth, onAuthStateChange } from './firebase';

export type ReferralEnvironment = 'dev' | 'prod';

export interface ReferralClaimResult {
  claimed: boolean;
  trial_days: number;
}

export type ReferralMobilePlatform = 'ios' | 'android';

export function referralSignInProvider(
  providerIds: readonly string[],
): 'Apple' | 'Google' | null {
  if (providerIds.length !== 1) return null;
  const providerId = providerIds[0];
  if (providerId === 'apple.com') return 'Apple';
  if (providerId === 'google.com') return 'Google';
  return null;
}

export function referralMobilePlatform(userAgent: string): ReferralMobilePlatform | null {
  if (/android/i.test(userAgent)) return 'android';
  if (/iPhone|iPad|iPod/i.test(userAgent)) return 'ios';
  return null;
}

export function referralDownloadURL(platform: ReferralMobilePlatform | null): string {
  if (platform === 'ios') return 'https://apps.apple.com/app/id6502156163';
  if (platform === 'android')
    return 'https://play.google.com/store/apps/details?id=com.friend.ios';
  return 'https://macos.omi.me';
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
  options: {
    user: Pick<User, 'uid' | 'getIdToken'>;
    deadlineMs?: number;
    isCurrent?: () => boolean;
  },
): Promise<ReferralClaimResult> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const owner = options.user;
  let invalidated = false;
  const unsubscribe = onAuthStateChange((user) => {
    if (user !== owner) invalidated = true;
  });
  const current = () =>
    !invalidated &&
    auth?.currentUser === owner &&
    !controller.signal.aborted &&
    (options.isCurrent?.() ?? true);
  const operation = async (): Promise<ReferralClaimResult> => {
    if (!current()) throw new ReferralClaimError('Referral attempt cancelled', false);
    let token: string | null;
    try {
      token = await owner.getIdToken();
    } catch {
      throw new ReferralClaimError('Sign-in token unavailable', true);
    }
    if (!current()) throw new ReferralClaimError('Referral attempt cancelled', false);
    // Token failures may be retried only under this captured auth session.
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
    if (!current()) throw new ReferralClaimError('Referral attempt cancelled', false);
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
    unsubscribe();
    if (timer !== undefined) clearTimeout(timer);
  }
}
