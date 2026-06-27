import 'package:omi/models/subscription.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';

bool shouldClearSyncRateLimitForPlan(Subscription subscription) {
  if (subscription.status != SubscriptionStatus.active) return false;
  return subscription.plan == PlanType.unlimited ||
      subscription.plan == PlanType.operator ||
      subscription.plan == PlanType.architect;
}

bool shouldClearSyncRateLimitForFairUseStatus(Map<String, dynamic>? status) {
  return status?['stage'] == 'none';
}

void reconcileSyncRateLimitWithSubscription(UserSubscriptionResponse? subscription) {
  if (subscription == null) return;
  if (shouldClearSyncRateLimitForPlan(subscription.subscription)) {
    SyncRateLimiter.instance.clear();
  }
}

void reconcileSyncRateLimitWithFairUseStatus(Map<String, dynamic>? status) {
  if (shouldClearSyncRateLimitForFairUseStatus(status)) {
    SyncRateLimiter.instance.clear();
  }
}
