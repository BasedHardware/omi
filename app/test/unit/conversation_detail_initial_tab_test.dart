import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';

TranscriptSegment _segment(String text) {
  return TranscriptSegment(
    id: 'segment-1',
    text: text,
    speaker: 'SPEAKER_0',
    isUser: true,
    personId: null,
    start: 0.24,
    end: 0.32,
    translations: [],
  );
}

ServerConversation _conversation({
  String overview = '',
  List<TranscriptSegment>? segments,
}) {
  return ServerConversation(
    id: 'conversation-1',
    createdAt: DateTime.utc(2026, 9, 21, 12),
    structured: Structured('Mm-hmm.', overview),
    transcriptSegments: segments ?? [_segment('Mm-hmm.')],
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    // A returning user has already seen the first-conversation review modal.
    SharedPreferences.setMockInitialValues({'has_first_conversation': true});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  test('opens a transcript-only fragment on Transcript', () {
    expect(conversationDetailInitialTabIndex(_conversation()), 0);
  });

  test('keeps normal summarized conversations on Summary', () {
    expect(
      conversationDetailInitialTabIndex(
        _conversation(overview: 'A useful summary.'),
      ),
      1,
    );
  });

  test(
    'preserves an explicit tab choice for transcript-only conversations',
    () {
      final conversation = _conversation();
      expect(
        conversationDetailInitialTabIndex(conversation, requestedTabIndex: 1),
        1,
      );
      expect(
        conversationDetailInitialTabIndex(conversation, requestedTabIndex: 2),
        2,
      );
    },
  );

  test('re-evaluates after detail hydration adds a summary', () {
    final conversation = _conversation();
    expect(conversationDetailInitialTabIndex(conversation), 0);

    conversation.structured.overview = 'Hydrated summary.';
    expect(conversationDetailInitialTabIndex(conversation), 1);
  });

  test('does not treat blank transcript segments as meaningful content', () {
    expect(
      conversationDetailInitialTabIndex(
        _conversation(segments: [_segment('  ')]),
      ),
      1,
    );
  });

  test(
    'keeps an in-progress capture on Summary until processing completes',
    () {
      final conversation = _conversation()..status = ConversationStatus.processing;
      expect(conversationDetailInitialTabIndex(conversation), 1);
    },
  );

  testWidgets('waits for detail hydration before auto-selecting Transcript', (tester) async {
    final initial = _conversation();
    final details = Completer<ServerConversation?>();
    final conversations = _conversationProvider(initial, details);
    final detail = ConversationDetailProvider();
    final apps = AppProvider();
    detail.setProviders(apps, conversations);
    addTearDown(() {
      detail.dispose();
      conversations.dispose();
      apps.dispose();
    });

    await tester.pumpWidget(_detailApp(initial, detail, conversations, apps));
    await tester.pump();
    expect(
      tester.state<ConversationDetailPageState>(find.byType(ConversationDetailPage)).selectedTab,
      ConversationTab.summary,
    );

    details.complete(initial);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      tester.state<ConversationDetailPageState>(find.byType(ConversationDetailPage)).selectedTab,
      ConversationTab.transcript,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('does not override a user Summary selection while details hydrate', (tester) async {
    final initial = _conversation();
    final details = Completer<ServerConversation?>();
    final conversations = _conversationProvider(initial, details);
    final detail = ConversationDetailProvider();
    final apps = AppProvider();
    detail.setProviders(apps, conversations);
    addTearDown(() {
      detail.dispose();
      conversations.dispose();
      apps.dispose();
    });

    await tester.pumpWidget(_detailApp(initial, detail, conversations, apps));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester
        .tap(find.byWidgetPredicate((widget) => widget is Semantics && widget.properties.label == 'Transcript'));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.byWidgetPredicate((widget) => widget is Semantics && widget.properties.label == 'Summary'));
    await tester.pump(const Duration(milliseconds: 300));

    details.complete(initial);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      tester.state<ConversationDetailPageState>(find.byType(ConversationDetailPage)).selectedTab,
      ConversationTab.summary,
    );
    expect(tester.takeException(), isNull);
  });
}

ConversationProvider _conversationProvider(
  ServerConversation initial,
  Completer<ServerConversation?> details,
) {
  final provider = ConversationProvider(isSignedIn: () => false);
  final date = conversationLocalDayKey(initial.createdAt);
  provider.conversations = [initial];
  provider.groupedConversations = {
    date: [initial]
  };
  provider.conversationDetailsFetcherOverride = (_) => details.future;
  return provider;
}

Widget _detailApp(
  ServerConversation initial,
  ConversationDetailProvider detail,
  ConversationProvider conversations,
  AppProvider apps, {
  int? initialTabIndex,
}) {
  return MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: MultiProvider(
      providers: [
        ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
        ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
        ChangeNotifierProvider<AppProvider>.value(value: apps),
        ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => [])),
        ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
        ChangeNotifierProvider(create: (_) => PeopleProvider()),
        ChangeNotifierProvider(
          create: (_) => IntegrationProvider(
            fetchStatus: (_) async => null,
            saveStatus: (_, __) async => false,
            deleteStatus: (_) async => false,
            persistPref: (_, __) async {},
          ),
        ),
      ],
      child: ConversationDetailPage(conversation: initial, initialTabIndex: initialTabIndex),
    ),
  );
}
