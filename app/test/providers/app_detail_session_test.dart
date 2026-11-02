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
  test('an old app detail read cannot populate the next account catalog', () async {
    SharedPreferencesUtil().uid = 'synthetic-old';
    final pending = Completer<Map<String, dynamic>?>();
    final provider = AppProvider()..appDetailsOverride = (_) => pending.future;
    addTearDown(provider.dispose);
    final read = provider.getAppDetails('app-1');
    provider.clearUserData();
    SharedPreferencesUtil().uid = 'synthetic-new';
    pending.complete({'id': 'app-1'});
    expect(await read, isNull);
    expect(provider.apps, isEmpty);
  });
}
