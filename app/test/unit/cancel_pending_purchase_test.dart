import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/cancel_pending_purchase.dart';

void main() {
  test('same price resubscribes, any other price is refused, and a live plan proceeds', () {
    expect(
      cancelPendingPurchase(cancelAtPeriodEnd: true, currentPriceId: 'price_plus_month', priceId: 'price_plus_month'),
      CancelPendingPurchase.resubscribe,
    );
    expect(
      cancelPendingPurchase(cancelAtPeriodEnd: true, currentPriceId: 'price_plus_month', priceId: 'price_plus_year'),
      CancelPendingPurchase.blocked,
    );
    expect(
      cancelPendingPurchase(cancelAtPeriodEnd: true, currentPriceId: null, priceId: 'price_plus_month'),
      CancelPendingPurchase.blocked,
    );
    expect(
      cancelPendingPurchase(cancelAtPeriodEnd: false, currentPriceId: 'price_plus_month', priceId: 'price_plus_year'),
      CancelPendingPurchase.proceed,
    );
    expect(isPendingCancelConflict(409), isTrue);
    expect(isPendingCancelConflict(400), isFalse);
  });
}
