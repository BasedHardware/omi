import type { User } from 'firebase/auth';
import { auth, onAuthStateChange } from './firebase';
import type { ReferralEnvironment } from './referrals';
import {
  safeHardwareCheckout,
  parseHardwareAttribution,
  type HardwareAttribution,
} from './hardwareReferralContract';

export class HardwareReferralError extends Error {
  constructor(public readonly detail: string, public readonly retryable = false) {
    super(detail);
  }
}

export async function attributeHardwareReferral(
  code: string,
  environment: ReferralEnvironment,
  options: {
    user: Pick<User, 'uid' | 'getIdToken'>;
    isCurrent: () => boolean;
    signal?: AbortSignal;
    deadlineMs?: number;
  },
): Promise<HardwareAttribution> {
  const owner = options.user;
  const controller = new AbortController();
  let invalidated = false;
  const invalidate = () => {
    invalidated = true;
    controller.abort();
  };
  const unsubscribe = onAuthStateChange((user) => {
    if (user !== owner) invalidate();
  });
  options.signal?.addEventListener('abort', invalidate);
  const current = () =>
    !invalidated &&
    !options.signal?.aborted &&
    !controller.signal.aborted &&
    auth?.currentUser === owner &&
    options.isCurrent();
  const requireCurrent = () => {
    if (!current()) throw new HardwareReferralError('cancelled');
  };
  let timer: ReturnType<typeof setTimeout> | undefined;
  const operation = async () => {
    requireCurrent();
    let token: string;
    try {
      token = await owner.getIdToken();
    } catch {
      throw new HardwareReferralError('token_unavailable', true);
    }
    requireCurrent();
    if (!token) throw new HardwareReferralError('token_unavailable', true);
    const response = await fetch('/api/referrals/hardware', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, environment }),
      signal: controller.signal,
    });
    requireCurrent();
    const body: unknown = await response.json();
    requireCurrent();
    if (!response.ok) {
      const detail =
        typeof body === 'object' &&
        body !== null &&
        'detail' in body &&
        typeof body.detail === 'string'
          ? body.detail
          : 'checkout_unavailable';
      throw new HardwareReferralError(
        detail,
        response.status === 429 || response.status >= 500,
      );
    }
    const result = parseHardwareAttribution(body);
    if (!result) throw new HardwareReferralError('checkout_unavailable', true);
    return result;
  };
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      invalidate();
      reject(new HardwareReferralError('checkout_unavailable', true));
    }, options.deadlineMs ?? 15_000);
  });
  try {
    return await Promise.race([operation(), timeout]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    unsubscribe();
    options.signal?.removeEventListener('abort', invalidate);
  }
}

export function hardwareReferralMessage(detail: string): string {
  switch (detail) {
    case 'invalid_referral_code':
      return 'This referral link is invalid. Ask your friend for a new link.';
    case 'self_referral':
      return 'You cannot use your own referral link.';
    case 'attribution_conflict':
      return 'This account already has a different referral.';
    case 'account_unavailable':
      return 'This account cannot use this referral.';
    case 'token_unavailable':
      return 'We could not confirm your sign-in. Try again.';
    default:
      return 'Referral checkout is unavailable right now. No discount has been confirmed. Please try again later.';
  }
}

export function navigateToHardwareCheckout(value: string): void {
  const url = safeHardwareCheckout(value);
  if (url) window.location.assign(url);
}
