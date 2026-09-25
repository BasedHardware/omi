import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/phone_calls/call_duration_format.dart';

void main() {
  group('formatPhoneCallDuration', () {
    test('uses m:ss below one hour (OmiDuration.offset)', () {
      expect(formatPhoneCallDuration(Duration.zero), '0:00');
      expect(formatPhoneCallDuration(const Duration(seconds: 9)), '0:09');
      expect(formatPhoneCallDuration(const Duration(minutes: 5, seconds: 3)), '5:03');
      expect(formatPhoneCallDuration(const Duration(minutes: 59, seconds: 59)), '59:59');
    });

    test('uses h:mm:ss at or above one hour', () {
      expect(formatPhoneCallDuration(const Duration(hours: 1)), '1:00:00');
      expect(formatPhoneCallDuration(const Duration(hours: 2, minutes: 7, seconds: 5)), '2:07:05');
      expect(formatPhoneCallDuration(const Duration(hours: 25, minutes: 1)), '25:01:00');
    });
  });
}
