import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('Omi button actions are enabled by default', () {
    expect(SharedPreferencesUtil().omiButtonActionsEnabled, isTrue);
  });

  test('Omi button actions setting persists changes', () {
    SharedPreferencesUtil().omiButtonActionsEnabled = false;
    expect(SharedPreferencesUtil().omiButtonActionsEnabled, isFalse);

    SharedPreferencesUtil().omiButtonActionsEnabled = true;
    expect(SharedPreferencesUtil().omiButtonActionsEnabled, isTrue);
  });
}
