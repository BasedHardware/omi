import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/wals/sync_rate_limit_reconciliation.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
  });

  test('clears stale rate limit when fair-use status is unrestricted', () {
    SyncRateLimiter.instance.markLimited(retryAfterSeconds: 3600);
    expect(SyncRateLimiter.instance.isLimited, isTrue);

    reconcileSyncRateLimitWithFairUseStatus({'stage': 'none'});

    expect(SyncRateLimiter.instance.isLimited, isFalse);
  });

  test('clears stale hard restriction after natural expiry normalizes to throttle', () {
    SyncRateLimiter.instance.markLimited(retryAfterSeconds: 3600);

    reconcileSyncRateLimitWithFairUseStatus({'stage': 'throttle'});

    expect(SyncRateLimiter.instance.isLimited, isFalse);
    expect(SyncRateLimiter.instance.hasPersistedFairUseState, isFalse);
  });

  test('keeps active rate limit when fair-use status is still restricted', () {
    SyncRateLimiter.instance.markLimited(retryAfterSeconds: 3600);

    reconcileSyncRateLimitWithFairUseStatus({'stage': 'restrict'});

    expect(SyncRateLimiter.instance.isLimited, isTrue);
  });

  test('clears persisted rate limit but preserves backendBusy cooldown', () {
    // Set both a persisted rate-limit and an in-memory backendBusy cooldown.
    // Use a longer backendBusy cooldown so `reason` reports it as the
    // dominant deadline (matching `until`'s max-based pick).
    SyncRateLimiter.instance.markLimited(retryAfterSeconds: 600, reason: RateLimitReason.fairUse);
    SyncRateLimiter.instance.markLimited(retryAfterSeconds: 3600, reason: RateLimitReason.backendBusy);
    expect(SyncRateLimiter.instance.isLimited, isTrue);
    expect(SyncRateLimiter.instance.reason, RateLimitReason.backendBusy);

    // A fair-use status refresh with stage: none should only clear the
    // persisted rate-limit, not the backendBusy cooldown.
    reconcileSyncRateLimitWithFairUseStatus({'stage': 'none'});

    expect(SyncRateLimiter.instance.isLimited, isTrue, reason: 'backendBusy cooldown should still be active');
    expect(SyncRateLimiter.instance.reason, RateLimitReason.backendBusy);
  });

  test('null fair-use status does not clear the cooldown', () {
    SyncRateLimiter.instance.markLimited(retryAfterSeconds: 3600);

    reconcileSyncRateLimitWithFairUseStatus(null);

    expect(SyncRateLimiter.instance.isLimited, isTrue);
  });

  test('unknown fair-use stage does not clear the cooldown', () {
    SyncRateLimiter.instance.markLimited(retryAfterSeconds: 3600);

    reconcileSyncRateLimitWithFairUseStatus({'stage': 'future_stage'});

    expect(SyncRateLimiter.instance.isLimited, isTrue);
  });

  group('clearRateLimit', () {
    test('only clears persisted rate-limit state, preserves backendBusy', () {
      SyncRateLimiter.instance.markLimited(retryAfterSeconds: 600, reason: RateLimitReason.fairUse);
      SyncRateLimiter.instance.markLimited(retryAfterSeconds: 3600, reason: RateLimitReason.backendBusy);

      SyncRateLimiter.instance.clearRateLimit();

      expect(SyncRateLimiter.instance.isLimited, isTrue);
      expect(SyncRateLimiter.instance.reason, RateLimitReason.backendBusy);
    });

    test('clears all when only persisted rate-limit was active', () {
      SyncRateLimiter.instance.markLimited(retryAfterSeconds: 3600, reason: RateLimitReason.fairUse);

      SyncRateLimiter.instance.clearRateLimit();

      expect(SyncRateLimiter.instance.isLimited, isFalse);
    });
  });
}
