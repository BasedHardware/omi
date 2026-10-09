import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/onboarding/find_device/found_devices.dart';

void main() {
  test('offline saved-device Retry invokes the connection callback', () async {
    var calls = 0;

    await retryOfflineSavedDevice(() async {
      calls++;
    });

    expect(calls, 1);
  });
}
