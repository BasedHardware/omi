import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/conversation_provider.dart';

App _app(String id, String name) => App(
      id: id,
      name: name,
      author: 'tester',
      description: 'test',
      image: '',
      capabilities: {'memories'},
      status: 'approved',
      category: 'test',
      approved: true,
      ratingCount: 0,
      enabled: true,
      deleted: false,
      isPaid: false,
      isUserPaid: false,
    );

ServerConversation _conversation() => ServerConversation(
      id: 'conv-1',
      createdAt: DateTime(2026, 7, 1, 9).toUtc(),
      structured: Structured('Sprint sync', 'Short compatibility paragraph.'),
    );

ConversationDetailProvider _providerWithApps(List<App> apps) {
  final provider = ConversationDetailProvider();
  addTearDown(provider.dispose);
  provider.selectedDate = conversationLocalDayKey(_conversation().createdAt);
  provider.setCachedConversation(_conversation());
  provider.appProvider = AppProvider()..apps = apps;
  return provider;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  // SCA-359: findAppById used to search only the two sheet caches, which fill
  // after the summary sheet fetch. A real app_id therefore rendered "Unknown
  // App" until the sheet was opened. The durable appProvider.apps catalog —
  // loaded at startup — is the fallback authority.
  group('findAppById', () {
    test('resolves an app from the durable provider catalog when sheet caches are empty', () {
      final provider = _providerWithApps([_app('app-1', 'My Template')]);

      final found = provider.findAppById('app-1');

      expect(found, isNotNull);
      expect(found!.name, 'My Template');
    });

    test('a null appId stays null so first-party summaries render as Summary', () {
      final provider = _providerWithApps([_app('app-1', 'My Template')]);

      expect(provider.findAppById(null), isNull);
    });

    test('an id present in no catalog still fails closed to null (Unknown App)', () {
      final provider = _providerWithApps([_app('app-1', 'My Template')]);

      expect(provider.findAppById('missing-app'), isNull);
    });
  });
}
