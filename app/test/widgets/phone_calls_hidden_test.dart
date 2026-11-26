import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/phone_calls/phone_calls_feature.dart';

void main() {
  test('phone calls are switched off', () => expect(PhoneCallsFeature.visible, isFalse));
}
