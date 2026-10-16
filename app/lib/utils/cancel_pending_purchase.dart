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

/// The upgrade route's only 409 is a pending cancellation. Checkout uses 400
/// for the same refusal; both carry this status so the client can say why.
bool isPendingCancelConflict(Object? statusCode) => statusCode == 409;

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
