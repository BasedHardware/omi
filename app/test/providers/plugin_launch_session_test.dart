import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/app_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  for (final replacement in ['other-account', 'original-account']) {
    test('retired launch details cannot populate a replacement/ABA catalog: $replacement', () async {
      SharedPreferencesUtil().uid = 'original-account';
      final pending = Completer<Map<String, dynamic>?>();
      final provider = AppProvider()..appDetailsOverride = (_) => pending.future;
      addTearDown(provider.dispose);
      final read = provider.getAppDetails('app-1');
      provider.clearUserData();
      SharedPreferencesUtil().uid = replacement;
      pending.complete({
        'id': 'app-1',
        'external_integration': {'app_home_url': 'https://plugin.test/old-grant'}
      });
      expect(await read, isNull);
      expect(provider.apps, isEmpty);
    });
  }
}
