import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/app_provider.dart';

class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

App _app({required bool enabled}) => App.fromJson({
      'id': 'app_journal',
      'name': 'Journal',
      'author': 'Test Author',
      'description': 'test',
      'image': '',
      'capabilities': ['memories'],
      'status': 'approved',
      'category': 'productivity',
      'approved': true,
      'private': false,
      'enabled': enabled,
      'deleted': false,
    });

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    Env.init(_UnreachableApiEnv());
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().appsList = [_app(enabled: true)];
  });

  test('a failed enabled-apps fetch keeps installed apps enabled', () async {
    final provider = AppProvider();
    addTearDown(provider.dispose);
    provider.retrieveAppsGroupedOverride = () async => [
          {
            'data': [_app(enabled: false)],
          },
        ];
    provider.getEnabledAppsOverride = getEnabledAppsServer;

    await provider.getApps();

    expect(provider.apps.singleWhere((app) => app.id == 'app_journal').enabled, isTrue);
  });

  test('a failed catalog fetch keeps the apps already saved', () async {
    final provider = AppProvider();
    addTearDown(provider.dispose);
    provider.retrieveAppsGroupedOverride = retrieveAppsGrouped;
    provider.getEnabledAppsOverride = () async => ['app_journal'];

    await provider.getApps();
    await Future<void>.delayed(const Duration(milliseconds: 600));

    expect(provider.apps.map((app) => app.id), ['app_journal']);
    expect(SharedPreferencesUtil().appsList.map((app) => app.id), ['app_journal']);
  });
}
