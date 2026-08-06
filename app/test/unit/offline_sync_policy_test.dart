import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';

void main() {
  test('historical offline auto-sync defaults off but preserves explicit opt-in', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();

    expect(SharedPreferencesUtil().autoSyncOfflineRecordings, isFalse);

    SharedPreferencesUtil().autoSyncOfflineRecordings = true;
    expect(SharedPreferencesUtil().autoSyncOfflineRecordings, isTrue);
  });
}
