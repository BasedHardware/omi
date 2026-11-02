/** Renew before API authentication expires; data freshness is bounded upstream. */
export function grafanaRenewalDelay(
  expiresAt: number,
  now = Date.now()
): number {
  return Math.max(1000, expiresAt - now - 60_000);
}
