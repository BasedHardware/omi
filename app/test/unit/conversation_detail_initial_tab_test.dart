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

ServerConversation _conversation({String overview = '', List<TranscriptSegment>? segments}) {
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
    expect(conversationDetailInitialTab(_conversation()), ConversationTab.transcript);
  });

  test('keeps normal summarized conversations on Summary', () {
    expect(conversationDetailInitialTab(_conversation(overview: 'A useful summary.')), ConversationTab.summary);
  });

  test('preserves an explicit tab choice for transcript-only conversations', () {
    final conversation = _conversation();
    expect(conversationDetailInitialTab(conversation, requested: ConversationTab.summary), ConversationTab.summary);
    expect(
      conversationDetailInitialTab(conversation, requested: ConversationTab.transcript),
      ConversationTab.transcript,
    );
  });

  test('re-evaluates after detail hydration adds a summary', () {
    final conversation = _conversation();
    expect(conversationDetailInitialTab(conversation), ConversationTab.transcript);

    conversation.structured.overview = 'Hydrated summary.';
    expect(conversationDetailInitialTab(conversation), ConversationTab.summary);
  });

  test('does not treat blank transcript segments as meaningful content', () {
    expect(conversationDetailInitialTab(_conversation(segments: [_segment('  ')])), ConversationTab.summary);
  });

  test('keeps an in-progress capture on Summary until processing completes', () {
    final conversation = _conversation()..status = ConversationStatus.processing;
    expect(conversationDetailInitialTab(conversation), ConversationTab.summary);
  });

  testWidgets('tabs read Summary then Transcript, with no Tasks tab even when it has tasks', (tester) async {
    final initial = _conversation(overview: 'A useful summary.');
    initial.structured.actionItems.add(ActionItem('Send the widget build'));
    final details = Completer<ServerConversation?>()..complete(initial);
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

    final summary = find.byKey(const Key('conversation_tab_summary'));
    final transcript = find.byKey(const Key('conversation_tab_transcript'));
    expect(find.descendant(of: summary, matching: find.text('Summary')), findsOneWidget);
    expect(find.descendant(of: transcript, matching: find.text('Transcript')), findsOneWidget);
    expect(tester.getCenter(summary).dx, lessThan(tester.getCenter(transcript).dx));
    expect(find.byType(Tab), findsNWidgets(2));
    expect(find.text('Tasks'), findsNothing);
    expect(
      tester.state<ConversationDetailPageState>(find.byType(ConversationDetailPage)).selectedTab,
      ConversationTab.summary,
    );

    // Visibility is no chip under the title. Private is the default and shows nothing; a shared
    // conversation gets a quiet label at the end of the tab row. Both reach the ⋯ menu.
    final visibility = find.byKey(const Key('conversation_visibility'));
    expect(visibility, findsNothing);
    expect(find.text('Private'), findsNothing);
    detail.updateVisibilityLocally(ConversationVisibility.shared);
    await tester.pump();
    expect(find.descendant(of: visibility, matching: find.text('Shared')), findsOneWidget);
    expect(tester.getCenter(visibility).dy, moreOrLessEquals(tester.getCenter(transcript).dy, epsilon: 1));
    expect(tester.getCenter(visibility).dx, greaterThan(tester.getCenter(transcript).dx));

    // Ask Omi left the top bar for the bottom bar; the summary template moved into the ⋯ menu.
    expect(find.byKey(const Key('conversation_ask_omi')), findsNothing);
    expect(find.byKey(const ValueKey('detail_ask_omi')), findsOneWidget);
    await tester.tap(find.byKey(const Key('conversation_more')));
    await tester.pumpAndSettle();
    expect(find.text('Summary Template'), findsOneWidget);
    expect(find.text('Visibility'), findsOneWidget);
    expect(tester.getCenter(find.text('Summary Template')).dy, lessThan(tester.getCenter(find.text('Visibility')).dy));
    expect(tester.takeException(), isNull);
  });

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
    await tester.tap(find.byKey(const Key('conversation_tab_transcript')));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.byKey(const Key('conversation_tab_summary')));
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

ConversationProvider _conversationProvider(ServerConversation initial, Completer<ServerConversation?> details) {
  final provider = ConversationProvider(isSignedIn: () => false);
  final date = conversationLocalDayKey(initial.createdAt);
  provider.conversations = [initial];
  provider.groupedConversations = {
    date: [initial],
  };
  provider.conversationDetailsFetcherOverride = (_) => details.future;
  return provider;
}

Widget _detailApp(
  ServerConversation initial,
  ConversationDetailProvider detail,
  ConversationProvider conversations,
  AppProvider apps, {
  ConversationTab? initialTab,
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
      child: ConversationDetailPage(conversation: initial, initialTab: initialTab),
    ),
  );
}
