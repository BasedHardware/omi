import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/capture/device_button_policy.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('device button actions stay enabled by default for existing users', () {
    expect(SharedPreferencesUtil().deviceButtonEnabled, isTrue);
    expect(DeviceButtonPolicy.shouldHandleAction(enabled: SharedPreferencesUtil().deviceButtonEnabled), isTrue);
  });

  test('disabled preference survives a preferences reload', () async {
    SharedPreferencesUtil().deviceButtonEnabled = false;
    await SharedPreferencesUtil.reload();

    expect(SharedPreferencesUtil().deviceButtonEnabled, isFalse);
    expect(DeviceButtonPolicy.shouldHandleAction(enabled: SharedPreferencesUtil().deviceButtonEnabled), isFalse);
  });

  test('disabled preference blocks user-configured button actions', () {
    expect(DeviceButtonPolicy.shouldHandleAction(enabled: false), isFalse);
  });
}
