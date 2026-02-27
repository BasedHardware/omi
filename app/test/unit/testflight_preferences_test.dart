import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';

void main() {
  group('SharedPreferencesUtil TestFlight API Environment', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    test('default testFlightApiEnvironment is production', () {
      expect(SharedPreferencesUtil().testFlightApiEnvironment, 'production');
    });

    test('default testFlightUseStagingApi is false', () {
      expect(SharedPreferencesUtil().testFlightUseStagingApi, isFalse);
    });

    test('setting production flips testFlightUseStagingApi to false', () {
      SharedPreferencesUtil().testFlightApiEnvironment = 'production';
      expect(SharedPreferencesUtil().testFlightApiEnvironment, 'production');
      expect(SharedPreferencesUtil().testFlightUseStagingApi, isFalse);
    });

    test('setting staging flips testFlightUseStagingApi to true', () {
      SharedPreferencesUtil().testFlightApiEnvironment = 'production';
      expect(SharedPreferencesUtil().testFlightUseStagingApi, isFalse);
      // Switch back
      SharedPreferencesUtil().testFlightApiEnvironment = 'staging';
      expect(SharedPreferencesUtil().testFlightUseStagingApi, isTrue);
    });

    test('persists through saveString', () async {
      final result = await SharedPreferencesUtil().saveString('testFlightApiEnvironment', 'production');
      expect(result, isTrue);
      expect(SharedPreferencesUtil().testFlightApiEnvironment, 'production');
    });
  });
}
