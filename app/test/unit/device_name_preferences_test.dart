import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('sets hardware name on first device connection', () {
    final prefs = SharedPreferencesUtil();

    prefs.updateDeviceNameOnConnect('device-a', 'Omi Alpha');

    expect(prefs.deviceName, 'Omi Alpha');
    expect(prefs.deviceNameDeviceId, 'device-a');
  });

  test('preserves custom name when reconnecting to the same device', () {
    final prefs = SharedPreferencesUtil();
    prefs.deviceName = 'Desk Omi';
    prefs.deviceNameDeviceId = 'device-a';

    prefs.updateDeviceNameOnConnect('device-a', 'Omi Alpha');

    expect(prefs.deviceName, 'Desk Omi');
    expect(prefs.deviceNameDeviceId, 'device-a');
  });

  test('resets to hardware name when switching devices', () {
    final prefs = SharedPreferencesUtil();
    prefs.deviceName = 'Desk Omi';
    prefs.deviceNameDeviceId = 'device-a';

    prefs.updateDeviceNameOnConnect('device-b', 'Omi Beta');

    expect(prefs.deviceName, 'Omi Beta');
    expect(prefs.deviceNameDeviceId, 'device-b');
  });

  test('fills empty stored name when reconnecting to the same device', () {
    final prefs = SharedPreferencesUtil();
    prefs.deviceName = '';
    prefs.deviceNameDeviceId = 'device-a';

    prefs.updateDeviceNameOnConnect('device-a', 'Omi Alpha');

    expect(prefs.deviceName, 'Omi Alpha');
    expect(prefs.deviceNameDeviceId, 'device-a');
  });
}
