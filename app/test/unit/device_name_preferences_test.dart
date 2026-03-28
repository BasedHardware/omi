import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';

void main() {
  group('SharedPreferencesUtil custom device names', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    test('saves and reads a custom name per device id', () async {
      final result = await SharedPreferencesUtil().saveCustomDeviceName('device-1', 'My Omi');

      expect(result, isTrue);
      expect(SharedPreferencesUtil().getCustomDeviceName('device-1'), 'My Omi');
    });

    test('falls back when no custom name exists', () {
      expect(SharedPreferencesUtil().getCustomDeviceName('missing-device', fallback: 'Omi'), 'Omi');
    });

    test('removes a custom device name when cleared', () async {
      await SharedPreferencesUtil().saveCustomDeviceName('device-1', 'My Omi');
      final result = await SharedPreferencesUtil().clearCustomDeviceName('device-1');

      expect(result, isTrue);
      expect(SharedPreferencesUtil().getCustomDeviceName('device-1', fallback: 'Omi'), 'Omi');
    });
  });
}
