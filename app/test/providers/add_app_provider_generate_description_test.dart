import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';

class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    Env.init(_UnreachableApiEnv());
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('a failed description generation keeps the description the user typed', () async {
    final provider = AddAppProvider();
    provider.appNameController.text = 'Standup Notes';
    provider.appDescriptionController.text = 'Turns my daily standups into a short list of blockers';

    await provider.generateDescription();

    expect(provider.appDescriptionController.text, 'Turns my daily standups into a short list of blockers');
    expect(provider.isGenratingDescription, isFalse);
  });
}
