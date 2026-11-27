import 'dart:async';

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
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_header.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/transcription_pending_conversations.dart';
import 'package:omi/services/experiments/summary_generation_gate.dart';
import 'package:omi/ui/ui.dart';
import '../helpers/reprocess_fakes.dart';
import '../helpers/transcription_hold_wire.dart';

TranscriptSegment _segment(String text) => TranscriptSegment(
      id: 'seg',
      text: text,
      speaker: 'SPEAKER_00',
      isUser: false,
      personId: null,
      start: 0,
      end: 1,
      translations: [],
    );

ServerConversation _conversation(
    {String title = 'Venue talk.', String overview = '', bool summaryRetryable = true, String? captureCoverage}) {
  return ServerConversation(
    id: 'detail-retry',
    createdAt: DateTime(2026, 9, 30, 12),
    structured: Structured(title, overview, emoji: '🧠'),
    transcriptSegments: [_segment('Venue talk. We picked Friday.')],
    summaryRetryable: summaryRetryable,
    captureCoverage: captureCoverage,
  );
}

ConversationDetailProvider _detail(ServerConversation conversation, {ConversationReprocessCall? reprocess}) {
  return ConversationDetailProvider(reprocess: reprocess)
    ..selectedDate = conversationLocalDayKey(conversation.createdAt)
    ..setCachedConversation(conversation)
    ..titleController = TextEditingController(text: conversation.structured.title)
    ..titleFocusNode = FocusNode();
}

Widget _app(ConversationDetailProvider detail, Widget body, {FolderProvider? folders}) {
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
      if (folders != null) ChangeNotifierProvider<FolderProvider>.value(value: folders),
    ],
    child: MaterialApp(
      theme: buildOmiTheme(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: body),
    ),
  );
}

Widget get _summary => const CustomScrollView(slivers: [GetAppsWidgets()]);

void main() {
  setUpAll(initHeldWireEnv);
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('an empty summary on a retryable row offers Summary failed · Retry, which reprocesses', (tester) async {
    final gate = Completer<ServerConversation?>();
    final calls = <String>[];
    final detail = _detail(
      _conversation(),
      reprocess: conversationReprocess((id, {appId, appIds, requireSpeakerReceipt = false, forceOmi = false}) {
        calls.add(id);
        return gate.future;
      }),
    );
    addTearDown(detail.dispose);

    await tester.pumpWidget(_app(detail, _summary));
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));

    expect(find.byKey(const Key('conversation_detail_summary_retry')), findsOneWidget);
    expect(find.text(l10n.conversationSummaryFailed), findsOneWidget);
    expect(find.text(l10n.noSummaryForConversation), findsNothing);

    await tester.tap(find.text(l10n.retry));
    await tester.pump();
    expect(calls, ['detail-retry']);
    expect(find.text(l10n.summarySummarizingWith(l10n.omiAppName)), findsOneWidget);

    gate.complete(_conversation(title: 'Venue planning', overview: 'Picked Friday.', summaryRetryable: false));
    await tester.pump();
    await tester.pump();
    expect(detail.conversation.summaryRetryable, isFalse);
    expect(find.byKey(const Key('conversation_detail_summary_retry')), findsNothing);
  });

  testWidgets('a held row\'s Retry answered 409 shows the not-transcribed notice and no action', (tester) async {
    TranscriptionPendingConversations.reset();
    addTearDown(TranscriptionPendingConversations.reset);
    final calls = <String>[];
    // The page opens with the Home row (a); its failed Home step offers Retry.
    final detail = _detail(heldListRow(), reprocess: heldWireReprocess(409, heldReprocess409Body, calls: calls));
    addTearDown(detail.dispose);

    await tester.pumpWidget(_app(detail, _summary));
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    await tester.tap(find.text(l10n.retry));
    await tester.pumpAndSettle();

    expect(calls, [heldConversationId]);
    expect(find.byKey(const Key('conversation_detail_transcription_pending')), findsOneWidget);
    expect(find.text(l10n.summaryTranscriptionPendingTitle), findsOneWidget);
    expect(find.text(l10n.retry), findsNothing);
    expect(find.text(l10n.generateSummary), findsNothing);
    expect(find.text(l10n.errorProcessingConversation), findsNothing);
    // The expiry timer must not outlive the test body.
    TranscriptionPendingConversations.reset();
  });

  testWidgets('a confirmed hold becomes processing and then shows its transcript and summary', (tester) async {
    var fetched = ServerConversation.fromJson({
      ...heldListRowJson(),
      'transcription_admission': 'allowance_held',
    });
    final detail = ConversationDetailProvider(fetchConversation: (_) async => fetched)
      ..selectedDate = conversationLocalDayKey(fetched.createdAt)
      ..setCachedConversation(fetched);
    addTearDown(detail.dispose);
    await tester.pumpWidget(_app(detail, _summary));
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));

    expect(find.byKey(const Key('conversation_detail_held_recording')), findsOneWidget);
    expect(find.text(l10n.waitingForTranscriptionAllowance), findsOneWidget);
    expect(find.text(l10n.retry), findsNothing);
    expect(find.text(l10n.upgrade), findsNothing);

    fetched = ServerConversation.fromJson({
      ...heldDetailJson(),
      'status': 'processing',
      'transcription_admission': 'processing',
    });
    expect(await detail.refreshConversation(), isTrue);
    await tester.pump();
    expect(detail.conversation.id, heldConversationId);
    expect(detail.conversation.homeStep, 'transcribing');
    expect(find.byKey(const Key('conversation_detail_held_recording')), findsNothing);
    expect(find.text(l10n.processingConversationProgress), findsOneWidget);
    expect(find.text(l10n.retry), findsNothing);

    fetched = ServerConversation.fromJson({
      ...heldDetailJson(),
      'transcription_wait': null,
      'structured': Structured('Venue planning', 'We picked Friday.', emoji: '🧠').toJson(),
      'transcript_segments': [_segment('We picked Friday.').toJson()],
    });
    expect(await detail.refreshConversation(), isTrue);
    await tester.pumpAndSettle();
    expect(detail.conversation.id, heldConversationId);
    expect(detail.conversation.transcriptSegments.single.text, 'We picked Friday.');
    expect(find.text(l10n.processingConversationProgress), findsNothing);
    expect(find.textContaining('We picked Friday.', findRichText: true), findsOneWidget);
  });

  testWidgets('redesign: a refresh that lands a transcript retires the not-transcribed card', (tester) async {
    TranscriptionPendingConversations.reset();
    addTearDown(TranscriptionPendingConversations.reset);
    SummaryGenerationV2Gate.debugOverride = true;
    addTearDown(() => SummaryGenerationV2Gate.debugOverride = null);
    var fetched = heldDetail();
    final detail = ConversationDetailProvider(
      reprocess: heldWireReprocess(409, heldReprocess409Body),
      fetchConversation: (_) async => fetched,
    )
      ..selectedDate = conversationLocalDayKey(heldDetail().createdAt)
      ..setCachedConversation(heldDetail());
    addTearDown(detail.dispose);

    await tester.pumpWidget(_app(detail, _summary));
    expect(await detail.reprocessConversation(), isFalse);
    await tester.pumpAndSettle();
    expect(detail.summaryFailure?.kind, SummaryFailureKind.transcriptionPending);

    // Still held: the card stays.
    expect(await detail.refreshConversation(), isTrue);
    expect(detail.summaryFailure?.kind, SummaryFailureKind.transcriptionPending);

    // Transcribed since: the card goes, and so does the marker.
    fetched = ServerConversation.fromJson({
      ...heldDetailJson(),
      'transcript_segments': [_segment('We picked Friday.').toJson()],
    });
    expect(await detail.refreshConversation(), isTrue);
    await tester.pumpAndSettle();
    expect(detail.summaryFailure, isNull);
    expect(TranscriptionPendingConversations.contains(heldConversationId), isFalse);
    TranscriptionPendingConversations.reset();
  });

  testWidgets('redesign: a busy card stays on a transcript-only refresh and goes once a summary lands', (tester) async {
    SummaryGenerationV2Gate.debugOverride = true;
    addTearDown(() => SummaryGenerationV2Gate.debugOverride = null);
    var fetched = _conversation(summaryRetryable: false);
    final detail = ConversationDetailProvider(
      reprocess: (id, {appId, appIds, requireSpeakerReceipt = false, forceOmi = false}) async => const ReprocessBusy(),
      fetchConversation: (_) async => fetched,
    )
      ..selectedDate = conversationLocalDayKey(fetched.createdAt)
      ..setCachedConversation(fetched);
    addTearDown(detail.dispose);

    await tester.pumpWidget(_app(detail, _summary));
    expect(await detail.reprocessConversation(), isFalse);
    expect(detail.summaryFailure?.kind, SummaryFailureKind.busy);
    expect(await detail.refreshConversation(), isTrue);
    expect(detail.summaryFailure?.kind, SummaryFailureKind.busy);

    fetched = _conversation(overview: 'Picked Friday.', summaryRetryable: false);
    expect(await detail.refreshConversation(), isTrue);
    expect(detail.summaryFailure, isNull);
    await tester.pumpAndSettle();
  });

  testWidgets('failed Home projection survives a legacy detail read and offers retry without a spinner',
      (tester) async {
    final legacy = _conversation(summaryRetryable: false);
    final processing = ServerConversation(
        id: legacy.id,
        createdAt: legacy.createdAt,
        structured: legacy.structured,
        status: ConversationStatus.processing);
    final detail = ConversationDetailProvider(fetchConversation: (_) async => processing)
      ..selectedDate = conversationLocalDayKey(processing.createdAt)
      ..setCachedConversation(processing.withHomeStep('failed'));
    addTearDown(detail.dispose);
    await detail.refreshConversation();
    expect(detail.conversation.homeStep, 'failed');
    await tester.pumpWidget(_app(detail, _summary));
    expect(find.byKey(const Key('conversation_detail_summary_retry')), findsOneWidget);
    expect(find.byType(OmiLoadingState), findsNothing);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('an empty summary without the server marker keeps the ordinary Generate Summary prompt', (tester) async {
    final detail = _detail(_conversation(summaryRetryable: false));
    addTearDown(detail.dispose);

    await tester.pumpWidget(_app(detail, _summary));
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));

    expect(find.byKey(const Key('conversation_detail_summary_retry')), findsNothing);
    expect(find.text(l10n.noSummaryForConversation), findsOneWidget);
  });

  testWidgets('an untitled legacy conversation hints its transcript text instead of Untitled', (tester) async {
    final detail = _detail(_conversation(title: '', summaryRetryable: false));
    final folders = FolderProvider(foldersFetcher: () async => []);
    addTearDown(detail.dispose);
    addTearDown(folders.dispose);

    await tester.pumpWidget(_app(detail, ConversationDetailHeader(onOpenRecordings: (_) {}), folders: folders));
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));

    final field = tester.widget<TextField>(find.descendant(
      of: find.byType(ConversationTitleField),
      matching: find.byType(TextField),
    ));
    expect(field.decoration!.hintText, 'Venue talk.');
    expect(field.decoration!.hintText, isNot(l10n.untitledConversation));
  });

  for (final coverage in <String?>['incomplete', 'mapped', 'unknown', null]) {
    testWidgets('detail shows partial recording only for incomplete coverage ($coverage)', (tester) async {
      final original = _conversation(captureCoverage: coverage);
      // Exercise the generated wire and app cache roundtrip before showing the header.
      final conversation = ServerConversation.fromJson(original.toGenerated().toJson());
      expect(conversation.captureCoverage, coverage);
      expect(ServerConversation.fromJson(conversation.toJson()).captureCoverage, coverage);
      final detail = _detail(conversation);
      final folders = FolderProvider(foldersFetcher: () async => []);
      addTearDown(detail.dispose);
      addTearDown(folders.dispose);
      await tester.pumpWidget(_app(detail, ConversationDetailHeader(onOpenRecordings: (_) {}), folders: folders));
      final badge = find.byKey(const Key('conversation_partial_recording'));
      expect(badge, coverage == 'incomplete' ? findsOneWidget : findsNothing);
      if (coverage == 'incomplete') {
        final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
        expect(find.text(l10n.partialRecording), findsOneWidget);
        await tester.pumpWidget(_app(
          detail,
          MediaQuery(
              data: const MediaQueryData(textScaler: TextScaler.linear(2)),
              child: ConversationDetailHeader(onOpenRecordings: (_) {})),
          folders: folders,
        ));
        expect(badge, findsOneWidget);
        expect(tester.takeException(), isNull);
      }
    });
  }

  test('existing nested coverage field is read without inferring coverage on legacy rows', () {
    final json = _conversation().toJson();
    json['capture_evidence'] = {'coverage': 'incomplete'};
    expect(ServerConversation.fromJson(json).captureCoverage, 'incomplete');
    json.remove('capture_evidence');
    expect(ServerConversation.fromJson(json).captureCoverage, isNull);
  });
}
