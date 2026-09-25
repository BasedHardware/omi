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

export async function claimReferralTrial(
  code: string,
  environment: ReferralEnvironment,
): Promise<ReferralClaimResult> {
  const token = await getIdToken();
  if (!token) throw new Error('Not authenticated');

  const response = await fetch('/api/referrals/claim', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ code, environment }),
  });
  if (!response.ok) {
    throw new Error(`Referral claim failed: ${response.status}`);
  }
  return response.json();
}
