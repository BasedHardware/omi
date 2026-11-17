import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
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
import 'package:omi/providers/transcription_pending_conversations.dart';
import 'package:omi/services/experiments/summary_generation_gate.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';

/// The page's MessageListener branch for REPROCESS_TRANSCRIPTION_PENDING.
ServerConversation _conversation({required bool failedRow}) {
  final conversation = ServerConversation(
    id: 'pending-page',
    createdAt: DateTime.utc(2026, 11, 16, 9),
    structured: Structured('Morning standup', failedRow ? '' : 'Agreed on the Friday launch.'),
    transcriptSegments: [
      TranscriptSegment(
        id: 's1',
        text: 'We agreed on Friday.',
        speaker: 'SPEAKER_0',
        isUser: true,
        personId: null,
        start: 0,
        end: 1,
        translations: [],
      ),
    ],
  );
  return failedRow ? conversation.withHomeStep('failed') : conversation;
}

Future<(ConversationDetailProvider, AppLocalizations)> _pumpPage(
    WidgetTester tester, ServerConversation initial) async {
  final conversations = ConversationProvider(isSignedIn: () => false)
    ..conversations = [initial]
    ..groupedConversations = {
      conversationLocalDayKey(initial.createdAt): [initial],
    }
    ..conversationDetailsFetcherOverride = (_) async => initial;
  final apps = AppProvider();
  final detail = ConversationDetailProvider(
    reprocess: (id, {appId, requireSpeakerReceipt = false, forceOmi = false}) async =>
        const ReprocessTranscriptionPending(),
  )..setProviders(apps, conversations);
  addTearDown(() {
    detail.dispose();
    conversations.dispose();
    apps.dispose();
  });
  await tester.pumpWidget(MaterialApp(
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
      child: ConversationDetailPage(conversation: initial, initialTab: ConversationTab.summary),
    ),
  ));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  final l10n = AppLocalizations.of(tester.element(find.byType(ConversationDetailPage)));
  return (detail, l10n);
}

Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
}

Future<void> _drain(WidgetTester tester) async {
  // Let any feedback timer run out before the test ends.
  await tester.pump(const Duration(seconds: 10));
  await tester.pumpWidget(const SizedBox());
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'has_first_conversation': true});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    TranscriptionPendingConversations.reset();
  });
  tearDown(() {
    SummaryGenerationV2Gate.debugOverride = null;
    TranscriptionPendingConversations.reset();
  });

  testWidgets('legacy: the in-place notice explains it, so no duplicate message', (tester) async {
    SummaryGenerationV2Gate.debugOverride = false;
    final (detail, l10n) = await _pumpPage(tester, _conversation(failedRow: true));
    expect(await detail.reprocessConversation(), isFalse);
    await _settle(tester);
    expect(find.byKey(const Key('conversation_detail_transcription_pending')), findsOneWidget);
    expect(find.text(l10n.summaryTranscriptionPendingBody), findsOneWidget);
    expect(find.text(l10n.errorProcessingConversation), findsNothing);
    await _drain(tester);
    // The expiry timer must not outlive the test body.
    TranscriptionPendingConversations.reset();
  });

  testWidgets('legacy: without the in-place notice it says so once, not as an error', (tester) async {
    SummaryGenerationV2Gate.debugOverride = false;
    final (detail, l10n) = await _pumpPage(tester, _conversation(failedRow: false));
    expect(await detail.reprocessConversation(), isFalse);
    await _settle(tester);
    expect(find.byKey(const Key('conversation_detail_transcription_pending')), findsNothing);
    expect(find.text(l10n.summaryTranscriptionPendingBody), findsOneWidget);
    expect(find.text(l10n.errorProcessingConversation), findsNothing);
    await _drain(tester);
    // The expiry timer must not outlive the test body.
    TranscriptionPendingConversations.reset();
  });

  testWidgets('legacy: a pending answer for another conversation says nothing here', (tester) async {
    SummaryGenerationV2Gate.debugOverride = false;
    final (detail, l10n) = await _pumpPage(tester, _conversation(failedRow: false));
    detail.lastFailedReprocessConversationId = 'another-conversation';
    detail.notifyInfo('REPROCESS_TRANSCRIPTION_PENDING');
    await _settle(tester);
    expect(find.text(l10n.summaryTranscriptionPendingBody), findsNothing);
    await _drain(tester);
  });

  testWidgets('redesign: the Summary card explains it in place with no extra message', (tester) async {
    SummaryGenerationV2Gate.debugOverride = true;
    final (detail, l10n) = await _pumpPage(tester, _conversation(failedRow: true));
    expect(await detail.reprocessConversation(), isFalse);
    await _settle(tester);
    expect(find.text(l10n.summaryTranscriptionPendingTitle), findsOneWidget);
    expect(find.text(l10n.summaryTranscriptionPendingBody), findsOneWidget);
    expect(find.text(l10n.errorProcessingConversation), findsNothing);
    await _drain(tester);
    // The expiry timer must not outlive the test body.
    TranscriptionPendingConversations.reset();
  });
}
