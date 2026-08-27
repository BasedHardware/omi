import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/phone_calls/call_duration_format.dart';

void main() {
  group('formatPhoneCallDuration', () {
    test('uses MM:SS below one hour', () {
      expect(formatPhoneCallDuration(Duration.zero), '00:00');
      expect(formatPhoneCallDuration(const Duration(seconds: 9)), '00:09');
      expect(formatPhoneCallDuration(const Duration(minutes: 5, seconds: 3)), '05:03');
      expect(formatPhoneCallDuration(const Duration(minutes: 59, seconds: 59)), '59:59');
    });

    test('uses HH:MM:SS at or above one hour', () {
      expect(formatPhoneCallDuration(const Duration(hours: 1)), '01:00:00');
      expect(formatPhoneCallDuration(const Duration(hours: 2, minutes: 7, seconds: 5)), '02:07:05');
      expect(formatPhoneCallDuration(const Duration(hours: 25, minutes: 1)), '25:01:00');
    });
  });
}
