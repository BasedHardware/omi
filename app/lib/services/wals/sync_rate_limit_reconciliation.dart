import 'package:omi/services/wals/sync_rate_limiter.dart';

bool shouldClearSyncRateLimitForFairUseStatus(Map<String, dynamic>? status) {
  final stage = status?['stage'];
  return stage == 'none' || stage == 'warning' || stage == 'throttle';
}

/// Reconcile the persisted fair-use rate-limit cooldown against the latest
/// server-reported fair-use status. When the server reports a known non-hard
/// stage (`none`, `warning`, or `throttle`), the restriction has been lifted,
/// so we clear the persisted HTTP-429 backoff — but only the persisted state,
/// not an active backend-busy cooldown (see [SyncRateLimiter.clearRateLimit]).
///
/// Note: a paid subscription alone is NOT sufficient to clear the cooldown.
/// The backend preserves abuse-derived restrict/throttle states even for
/// paid users (`backend/utils/fair_use.py`), so we rely on the fair-use
/// status endpoint as the authoritative signal.
void reconcileSyncRateLimitWithFairUseStatus(Map<String, dynamic>? status) {
  if (shouldClearSyncRateLimitForFairUseStatus(status)) {
    SyncRateLimiter.instance.clearRateLimit();
  }
}
