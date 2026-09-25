/// Every conversation action records one `Conversation Action` event with only its action and the
/// surface it came from (David, 2026-09-24: learn which actions earn their place).
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/conversation_action_analytics.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

ServerConversation _conversation(String id) => ServerConversation(
      id: id,
      createdAt: DateTime(2026, 9, 20, 10),
      structured: Structured('Design review', 'Overview', emoji: '🧠'),
      status: ConversationStatus.completed,
    );

void main() {
  late _RecordingAdapter adapter;

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    adapter = _RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
  });
  tearDown(AnalyticsManager.resetForTesting);

  Future<List<Map<String, Object>>> actions() async {
    await AnalyticsManager.flushPending(force: true);
    // The manager adds its own app_* provenance to every event; the event itself carries only these.
    return adapter.events
        .where((e) => e.$1 == 'Conversation Action')
        .map((e) => Map<String, Object>.fromEntries(e.$2.entries.where((p) => !p.key.startsWith('app_'))))
        .toList();
  }

  test('the event carries only the action and the surface, for every action and surface', () async {
    const surfaces = ConversationActionSurface.values;
    for (final (i, action) in ConversationActionAction.values.indexed) {
      trackConversationAction(action, surfaces[i % surfaces.length]);
    }
    final events = await actions();
    expect(events, hasLength(ConversationActionAction.values.length));
    expect(events.map((e) => e['surface']).toSet(), surfaces.map((s) => s.wireName).toSet());
    for (final properties in events) {
      expect(properties.keys.toSet(), {'action', 'surface'});
    }
    expect(events.first, {'action': 'ask_omi', 'surface': 'top_bar'});
  });

  group('conversation page', () {
    late ConversationProvider conversations;
    late AppProvider apps;
    late ConversationDetailProvider detail;
    late FolderProvider folders;
    late ServerConversation item;

    setUp(() {
      conversations = ConversationProvider(isSignedIn: () => false);
      apps = AppProvider();
      detail = ConversationDetailProvider();
      folders = FolderProvider(foldersFetcher: () async => []);
      item = _conversation('detail-1');
      conversations.conversations = [item];
      conversations.conversationDetailsFetcherOverride = (id) async => item;
      detail.setProviders(apps, conversations);
      detail.setCachedConversation(item);
    });

    Future<void> pumpPage(WidgetTester tester) async {
      await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
          ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
          ChangeNotifierProvider<AppProvider>.value(value: apps),
          ChangeNotifierProvider<FolderProvider>.value(value: folders),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: ConversationDetailPage(conversation: item),
        ),
      ));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
    }

    testWidgets('Star, Share and the overflow each record their surface', (tester) async {
      await pumpPage(tester);

      await tester.tap(find.byKey(const Key('conversation_star')));
      await tester.pump();
      await tester.tap(find.byKey(const Key('conversation_share')));
      await tester.pump();
      // Share asks before making a private conversation public; leave it private.
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('conversation_more')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Rename'));
      await tester.pumpAndSettle();

      final events = await tester.runAsync(actions);
      expect(events, [
        {'action': 'star', 'surface': 'top_bar'},
        {'action': 'share', 'surface': 'top_bar'},
        {'action': 'rename', 'surface': 'overflow'},
      ]);
      await tester.pumpWidget(const SizedBox());
    });
  });

  group('conversation row', () {
    late ConversationProvider provider;

    setUp(() {
      provider = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
        isSignedIn: () => true,
      );
    });
    tearDown(() => provider.dispose());

    Future<void> pumpRow(WidgetTester tester, ServerConversation conversation) async {
      provider.conversations = [conversation];
      await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider<ConversationProvider>.value(value: provider),
          ChangeNotifierProvider<ConnectivityProvider>(create: (_) => ConnectivityProvider()),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: ConversationListItem(conversation: conversation, date: DateTime(2026, 9, 20), conversationIdx: 0),
          ),
        ),
      ));
    }

    testWidgets('a long-press menu choice records row_long_press', (tester) async {
      await pumpRow(tester, _conversation('a'));
      await tester.longPress(find.byType(ConversationListItem));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('conversation_action_select')));
      await tester.pumpAndSettle();
      expect(await tester.runAsync(actions), [
        {'action': 'select', 'surface': 'row_long_press'},
      ]);
    });

    testWidgets('a swipe to delete records row_swipe', (tester) async {
      await pumpRow(tester, _conversation('b'));
      await tester.fling(find.byType(Dismissible), const Offset(-600, 0), 2000);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(await tester.runAsync(actions), [
        {'action': 'delete', 'surface': 'row_swipe'},
      ]);
    });
  });
}

class _RecordingAdapter implements AnalyticsAdapter {
  final events = <(String, Map<String, Object>)>[];
  bool initialized = false;

  @override
  bool get isInitialized => initialized;

  @override
  Future<void> init() async => initialized = true;

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void alias({required String newUserId}) {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) =>
      events.add((eventName, properties ?? const {}));

  @override
  void setInteractionContext({String? screenName, required String target}) {}

  @override
  void registerSuperProperties(Map<String, Object> properties) {}

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}
