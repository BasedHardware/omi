import 'package:flutter/widgets.dart';

import 'package:omi/ui/ui.dart';

/// What a purchase tap means while cancellation may still be pending.
enum CancelPendingPurchase { resubscribe, blocked, proceed }

/// Same-price taps reactivate. Every other price is refused until that happens.
CancelPendingPurchase cancelPendingPurchase({
  required bool cancelAtPeriodEnd,
  required String? currentPriceId,
  required String priceId,
}) {
  if (!cancelAtPeriodEnd) return CancelPendingPurchase.proceed;
  if (currentPriceId != null && currentPriceId.isNotEmpty && priceId == currentPriceId) {
    return CancelPendingPurchase.resubscribe;
  }
  return CancelPendingPurchase.blocked;
}

/// Upgrade 409 can mean cancellation or a stale currency offer. Preserve the
/// cancellation message for legacy responses without detail, while showing
/// other conflicts as returned. Checkout's 409 has a separate meaning.
bool isUpgradePendingCancelConflict(Object? statusCode, {String? detail}) =>
    statusCode == 409 &&
    (detail == null ||
        detail ==
            'Plan changes are available after the current subscription ends. Reactivate your current plan to keep it.');

/// Stripe period timestamps are unix seconds. Null when the value is not a date.
String? billingDateLabel(BuildContext context, Object? raw) {
  final seconds = raw is int
      ? raw
      : raw is num
          ? raw.toInt()
          : null;
  if (seconds == null || seconds <= 0) return null;
  return OmiDateFormat.of(context).date(DateTime.fromMillisecondsSinceEpoch(seconds * 1000));
}
