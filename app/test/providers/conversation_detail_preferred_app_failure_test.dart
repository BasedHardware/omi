import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';

class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() => Env.init(_UnreachableApiEnv()));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().preferredSummarizationAppId = 'app-old';
  });

  test('a rejected default app write keeps the previous default', () async {
    final provider = ConversationDetailProvider();
    addTearDown(provider.dispose);
    provider.loadPreferredSummarizationApp();

    provider.setPreferredSummarizationApp('app-new');
    await Future<void>.delayed(const Duration(milliseconds: 200));

    expect(provider.preferredSummarizationAppId, 'app-old');
    expect(SharedPreferencesUtil().preferredSummarizationAppId, 'app-old');
  });
}
