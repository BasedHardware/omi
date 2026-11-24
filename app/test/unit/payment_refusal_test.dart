// Stripe checkout and charge refusals for readers who must buy through Google Play arrive as readable
// text with their code, never as a JSON string a surface would show raw.
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/payment.dart';

void main() {
  test('use_google_play gives its sentence and code', () {
    final result = paymentErrorFromBody(
        409, '{"detail": {"code": "use_google_play", "message": "Subscribe with Google Play in the app."}}');
    expect(result['error'], isTrue);
    expect(result['status_code'], 409);
    expect(result['code'], 'use_google_play');
    expect(result['detail'], 'Subscribe with Google Play in the app.');
    expect(paymentRefusalMessage(result), 'Subscribe with Google Play in the app.');
  });

  test('a Play subscription on hold gives its sentence', () {
    final result = paymentErrorFromBody(
        403,
        '{"detail": {"code": "play_subscription_on_hold", '
        '"message": "You have a Google Play subscription on hold. Fix the payment in Google Play."}}');
    expect(
        paymentRefusalMessage(result), 'You have a Google Play subscription on hold. Fix the payment in Google Play.');
  });

  test('a top-level code and message is read the same way', () {
    final result =
        paymentErrorFromBody(409, '{"code": "use_google_play", "message": "Subscribe with Google Play in the app."}');
    expect(paymentRefusalMessage(result), 'Subscribe with Google Play in the app.');
  });

  test('a bare code is never shown as text', () {
    final result = paymentErrorFromBody(409, '{"detail": "use_google_play"}');
    expect(result['code'], 'use_google_play');
    expect(result.containsKey('detail'), isFalse);
    expect(paymentRefusalMessage(result), isNull);
  });

  test('a coded refusal without a message leaves the surface its own text', () {
    final result = paymentErrorFromBody(409, '{"detail": {"code": "use_google_play"}}');
    expect(result.containsKey('detail'), isFalse);
    expect(paymentRefusalMessage(result), isNull);
  });

  test('today\'s plain sentence refusals keep their detail and stay uncoded', () {
    const sentence =
        'Plan changes are available after the current subscription ends. Reactivate your current plan to keep it.';
    final result = paymentErrorFromBody(409, '{"detail": "$sentence"}');
    expect(result['detail'], sentence);
    expect(result.containsKey('code'), isFalse);
    expect(paymentRefusalMessage(result), isNull);
  });

  test('a body that is not JSON gives only the status', () {
    expect(paymentErrorFromBody(409, 'upstream error'), {'error': true, 'status_code': 409});
  });
}
