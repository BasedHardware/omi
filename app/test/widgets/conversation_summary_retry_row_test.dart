import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/transcription_pending_conversations.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/conversations/conversation_title.dart';
import 'package:omi/ui/format/omi_date_format.dart';

import '../helpers/transcription_hold_wire.dart';

TranscriptSegment _segment(String text) {
  return TranscriptSegment(
    id: 'seg',
    text: text,
    speaker: 'SPEAKER_00',
    isUser: false,
    personId: null,
    start: 0,
    end: 1,
    translations: [],
  );
}

ServerConversation _conversation({
  String id = 'c1',
  String title = 'We picked the venue for Friday.',
  ConversationStatus status = ConversationStatus.completed,
  List<TranscriptSegment>? segments,
  String emoji = '',
  bool summaryRetryable = true,
}) {
  return ServerConversation(
    id: id,
    createdAt: DateTime.utc(2020, 1, 1, 12),
    structured: Structured(title, '', emoji: emoji),
    status: status,
    transcriptSegments: segments ?? [_segment('We picked the venue for Friday.')],
    summaryRetryable: summaryRetryable,
  );
}

Finder get _indicator => find.byKey(const Key('conversation_summary_failed_indicator'));
Finder get _retryButton => find.byKey(const Key('conversation_summary_retry_button'));

AppLocalizations _l10n(WidgetTester tester) => AppLocalizations.of(tester.element(find.byType(Scaffold)));

Future<ConversationProvider> _pumpRow(
  WidgetTester tester, {
  required ServerConversation conversation,
  Future<ServerConversation?> Function(String conversationId)? reprocess,
  Future<ReprocessResult> Function(String conversationId)? reprocessResult,
}) async {
  final provider = ConversationProvider(
    conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
    isSignedIn: () => true,
  )..conversations = [conversation];
  addTearDown(provider.dispose);

  await tester.pumpWidget(
    ChangeNotifierProvider<ConversationProvider>.value(
      value: provider,
      child: MaterialApp(
        navigatorKey: globalNavigatorKey,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: Consumer<ConversationProvider>(
            builder: (context, conversations, _) {
              if (conversations.conversations.isEmpty) {
                return conversations.processingConversations.isEmpty
                    ? const SizedBox.shrink()
                    : const Text('moved-to-processing');
              }
              return ConversationListItem(
                conversation: conversations.conversations.first,
                date: DateTime.utc(2020),
                conversationIdx: 0,
                reprocess: reprocessResult ??
                    (reprocess == null ? null : (id) async => ReprocessResult.fromConversation(await reprocess(id))),
              );
            },
          ),
        ),
      ),
    ),
  );
  await tester.pump();
  return provider;
}

void main() {
  setUpAll(initHeldWireEnv);
  final emitted = <ConversationUntitledRendered>[];

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    emitted.clear();
    UntitledConversationTelemetry.resetForTest();
    UntitledConversationTelemetry.sinkOverride = emitted.add;
  });

  tearDown(UntitledConversationTelemetry.resetForTest);

  testWidgets('a retryable row shows its deterministic title with Summary failed · Retry', (tester) async {
    await _pumpRow(tester, conversation: _conversation());

    expect(find.text('We picked the venue for Friday.'), findsOneWidget);
    expect(_indicator, findsOneWidget);
    expect(_retryButton, findsOneWidget);
    expect(find.text(_l10n(tester).conversationSummaryFailed), findsOneWidget);
    expect(find.text(_l10n(tester).retry), findsOneWidget);
    expect(emitted, isEmpty);
  });

  testWidgets('an age-failed processing row is terminal and its existing Retry starts a new attempt', (tester) async {
    final calls = <String>[];
    final provider = await _pumpRow(
      tester,
      conversation: _conversation(title: 'Processing', status: ConversationStatus.processing, summaryRetryable: false)
          .withHomeStep('failed'),
      reprocess: (id) async {
        calls.add(id);
        return _conversation(status: ConversationStatus.processing, summaryRetryable: false);
      },
    );
    expect(find.text("Omi couldn't finish"), findsOneWidget);
    expect(find.text('Processing'), findsNothing);
    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(_retryButton, findsOneWidget);
    await tester.tap(_retryButton);
    await tester.pumpAndSettle();
    expect(calls, ['c1']);
    expect(provider.processingConversations, hasLength(1));
    provider.removeProcessingConversation('c1');
    await tester.pump();
  });

  for (final homeStep in <String?>['failed', null]) {
    testWidgets('calendar link/unlink keeps row presentation for home_step=$homeStep', (tester) async {
      final original = _conversation(status: ConversationStatus.processing, summaryRetryable: false);
      final provider =
          await _pumpRow(tester, conversation: homeStep == null ? original : original.withHomeStep(homeStep));
      final event = CalendarEventLink(
          eventId: 'planning',
          title: 'Planning',
          startTime: original.createdAt,
          endTime: original.createdAt.add(const Duration(hours: 1)));
      final detail = ConversationDetailProvider(
        linkCalendar: (id, eventId) async {
          expect(id, 'c1');
          expect(eventId, event.eventId);
          return event;
        },
        unlinkCalendar: (_) async => true,
        autoLinkCalendar: (_) async => event,
      )
        ..conversationProvider = provider
        ..selectedDate = conversationLocalDayKey(original.createdAt)
        ..setCachedConversation(provider.conversations.single);
      addTearDown(detail.dispose);
      void expectPresentation() {
        expect(provider.conversations.single.homeStep, homeStep);
        expect(find.text("Omi couldn't finish"), homeStep == 'failed' ? findsOneWidget : findsNothing);
        expect(_retryButton, homeStep == 'failed' ? findsOneWidget : findsNothing);
        if (homeStep == null) expect(find.text(original.structured.title), findsOneWidget);
        expect(find.byType(CircularProgressIndicator), findsNothing);
      }

      expect(await detail.linkCalendarEvent(event.eventId), same(event));
      await tester.pump();
      expect(provider.conversations.single.calendarEvent, same(event));
      expectPresentation();
      expect(await detail.unlinkCalendarEvent(), isTrue);
      await tester.pump();
      expect(provider.conversations.single.calendarEvent, isNull);
      expectPresentation();
      expect(await detail.autoLinkCalendarEvent(), same(event));
      await tester.pump();
      expectPresentation();
    });
  }

  // Held-recording rows use the real wire copies in ../helpers/transcription_hold_wire.dart:
  // (a) the Home row, (b) the detail copy, (c) the 200 waiting answer and (d) the 409 body.
  Future<ReprocessResult> Function(String) wire(int status, Object body) =>
      (id) => reProcessConversationServer(id, send: (_) async => heldJsonResponse(status, body));
  Finder pendingIndicator() => find.byKey(const Key('conversation_transcription_pending_indicator'));
  ServerConversation listRow({String? id, String? homeStep, String? title, bool? summaryRetryable}) =>
      ServerConversation.fromJson({
        ...heldListRowJson(),
        if (id != null) 'id': id,
        if (homeStep != null) 'home_step': homeStep,
        if (summaryRetryable != null) 'summary_retryable': summaryRetryable,
        if (title != null) 'structured': {...heldListRowJson()['structured'] as Map<String, dynamic>, 'title': title},
      });

  testWidgets('a held row answered 409 says Not transcribed yet once, as its title, with no error', (tester) async {
    TranscriptionPendingConversations.reset();
    addTearDown(TranscriptionPendingConversations.reset);
    await _pumpRow(tester, conversation: heldListRow(), reprocessResult: wire(409, heldReprocess409Body));
    expect(_retryButton, findsOneWidget);
    await tester.tap(_retryButton);
    await tester.pumpAndSettle();
    final l10n = _l10n(tester);
    expect(find.text(l10n.somethingWentWrong), findsNothing);
    expect(_retryButton, findsNothing);
    // The server's stand-in title gives way to the status, shown once; the slot is omitted.
    expect(find.text(l10n.summaryTranscriptionPendingTitle), findsOneWidget);
    expect(find.text(TranscriptionPendingConversations.serverHoldTitle), findsNothing);
    expect(pendingIndicator(), findsNothing);
    TranscriptionPendingConversations.reset();
  });

  testWidgets('a titled held row answered 409 keeps its title and shows the status once, in the slot', (tester) async {
    TranscriptionPendingConversations.reset();
    addTearDown(TranscriptionPendingConversations.reset);
    // The 409 path also covers a held row someone titled; its title is not the stand-in.
    await _pumpRow(
      tester,
      conversation: listRow(title: 'Standup with Ana'),
      reprocessResult: wire(409, heldReprocess409Body),
    );
    await tester.tap(_retryButton);
    await tester.pumpAndSettle();
    expect(find.text('Standup with Ana'), findsOneWidget);
    expect(pendingIndicator(), findsOneWidget);
    expect(find.text(_l10n(tester).summaryTranscriptionPendingTitle), findsOneWidget);
    expect(_retryButton, findsNothing);
    TranscriptionPendingConversations.reset();
  });

  testWidgets('a retry inside the transcription window shows the server waiting state, not an error', (tester) async {
    TranscriptionPendingConversations.reset();
    addTearDown(TranscriptionPendingConversations.reset);
    final provider =
        await _pumpRow(tester, conversation: heldListRow(), reprocessResult: wire(200, heldRetryWaitingJson()));
    await tester.tap(_retryButton);
    await tester.pumpAndSettle();
    expect(find.text(_l10n(tester).somethingWentWrong), findsNothing);
    expect(find.text('moved-to-processing'), findsOneWidget);
    expect(provider.processingConversations.single.homeStep, 'transcribing');
    // The copy carries the answer; no session status is kept for it.
    expect(TranscriptionPendingConversations.contains(heldConversationId), isFalse);

    // End the processing row so its reconcile timer cancels within the test body.
    provider.removeProcessingConversation(heldConversationId);
    await tester.pump();
  });

  testWidgets('a failed attempt is an error even after another surface marked a different row', (tester) async {
    TranscriptionPendingConversations.reset();
    addTearDown(TranscriptionPendingConversations.reset);
    TranscriptionPendingConversations.mark('other');
    await _pumpRow(
      tester,
      conversation: heldListRow(),
      reprocessResult: (_) async => const ReprocessFailed(statusCode: 500),
    );
    await tester.tap(_retryButton);
    await tester.pumpAndSettle();
    expect(find.text(_l10n(tester).somethingWentWrong), findsOneWidget);
    expect(_retryButton, findsOneWidget);
    expect(TranscriptionPendingConversations.contains(heldConversationId), isFalse);
    TranscriptionPendingConversations.reset();
  });

  testWidgets('the row follows the not-transcribed set without a tap, and a settled copy clears it', (tester) async {
    TranscriptionPendingConversations.reset();
    addTearDown(TranscriptionPendingConversations.reset);
    final provider = await _pumpRow(tester, conversation: heldListRow());
    expect(_retryButton, findsOneWidget);

    TranscriptionPendingConversations.mark(heldConversationId);
    await tester.pump();
    expect(_retryButton, findsNothing);
    expect(find.text(_l10n(tester).summaryTranscriptionPendingTitle), findsOneWidget);

    // A newer list copy: transcribed and summarized, so the Home step is ready.
    provider.updateConversation(listRow(homeStep: 'ready', title: 'Venue planning'), preserveHomeStep: false);
    await tester.pump();
    expect(TranscriptionPendingConversations.contains(heldConversationId), isFalse);
    expect(find.text('Venue planning'), findsOneWidget);
  });

  testWidgets('opening the detail page keeps the not-transcribed row: its copy has no home_step', (tester) async {
    TranscriptionPendingConversations.reset();
    addTearDown(TranscriptionPendingConversations.reset);
    final provider = await _pumpRow(tester, conversation: heldListRow());
    TranscriptionPendingConversations.mark(heldConversationId);
    await tester.pump();

    final detailCopy = heldDetail();
    expect(detailCopy.homeStep, isNull);
    final detail = ConversationDetailProvider(fetchConversation: (_) async => detailCopy)
      ..conversationProvider = provider
      ..selectedDate = conversationLocalDayKey(detailCopy.createdAt)
      ..setCachedConversation(provider.conversations.single);
    addTearDown(detail.dispose);
    expect(await detail.refreshConversation(), isTrue);
    await tester.pump();

    expect(provider.conversations.single.homeStep, 'failed');
    expect(TranscriptionPendingConversations.contains(heldConversationId), isTrue);
    expect(find.text(_l10n(tester).summaryTranscriptionPendingTitle), findsOneWidget);
    expect(_retryButton, findsNothing);
    expect(find.text(_l10n(tester).conversationSummaryFailed), findsNothing);
    TranscriptionPendingConversations.reset();
  });

  testWidgets('a detail copy with a transcript clears the status and brings Retry back', (tester) async {
    TranscriptionPendingConversations.reset();
    addTearDown(TranscriptionPendingConversations.reset);
    final provider = await _pumpRow(tester, conversation: heldListRow());
    TranscriptionPendingConversations.mark(heldConversationId);
    await tester.pump();
    expect(_retryButton, findsNothing);

    // Transcribed since, but the summary pass failed: the hold no longer applies, the row is retryable.
    final detailCopy = ServerConversation.fromJson({
      ...heldDetailJson(),
      'summary_retryable': true,
      'structured': {...heldDetailJson()['structured'] as Map<String, dynamic>, 'title': ''},
      'transcript_segments': [_segment('We picked Friday.').toJson()],
    });
    final detail = ConversationDetailProvider(fetchConversation: (_) async => detailCopy)
      ..conversationProvider = provider
      ..selectedDate = conversationLocalDayKey(detailCopy.createdAt)
      ..setCachedConversation(provider.conversations.single);
    addTearDown(detail.dispose);
    expect(await detail.refreshConversation(), isTrue);
    await tester.pump();

    expect(TranscriptionPendingConversations.contains(heldConversationId), isFalse);
    expect(_retryButton, findsOneWidget);
  });

  test('a list replacement clears the status only for rows the server settled', () async {
    TranscriptionPendingConversations.reset();
    addTearDown(TranscriptionPendingConversations.reset);
    for (final id in ['settled', 'retryable', 'still-held']) {
      TranscriptionPendingConversations.mark(id);
    }
    final provider = ConversationProvider(
      conversationListFetcher: () async => (
        items: [
          // List rows omit transcripts: only the Home step and the retryable marker speak.
          listRow(id: 'settled', homeStep: 'ready', title: 'Venue planning'),
          listRow(id: 'retryable', title: '', summaryRetryable: true),
          listRow(id: 'still-held'),
        ],
        ok: true,
      ),
      conversationCacheLoader: () async => [],
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    expect(await provider.fetchConversations(), isTrue);
    expect(TranscriptionPendingConversations.contains('settled'), isFalse);
    expect(TranscriptionPendingConversations.contains('retryable'), isFalse);
    expect(TranscriptionPendingConversations.contains('still-held'), isTrue);
  });

  testWidgets('Retry comes back on its own when the not-transcribed answer expires', (tester) async {
    TranscriptionPendingConversations.reset();
    addTearDown(TranscriptionPendingConversations.reset);
    await _pumpRow(tester, conversation: heldListRow());
    TranscriptionPendingConversations.mark(heldConversationId);
    await tester.pump();
    expect(_retryButton, findsNothing);

    await tester.pump(TranscriptionPendingConversations.ttl - const Duration(seconds: 1));
    expect(_retryButton, findsNothing);
    // Nothing else changes: only the expiry rebuilds the row.
    await tester.pump(const Duration(seconds: 1));
    expect(TranscriptionPendingConversations.contains(heldConversationId), isFalse);
    expect(find.text(_l10n(tester).summaryTranscriptionPendingTitle), findsNothing);
    expect(_retryButton, findsOneWidget);
  });

  testWidgets('a row the model found nothing in keeps its title and offers no retry', (tester) async {
    await _pumpRow(tester, conversation: _conversation(summaryRetryable: false));

    expect(find.text('We picked the venue for Friday.'), findsOneWidget);
    expect(_indicator, findsNothing);
    expect(_retryButton, findsNothing);
  });

  testWidgets('a legacy untitled row shows transcript text, not Untitled, and no guessed retry', (tester) async {
    await _pumpRow(
      tester,
      conversation: _conversation(
        title: '',
        summaryRetryable: false,
        segments: [_segment('one two three four five six seven')],
      ),
    );

    expect(find.text('one two three four five six seven'), findsOneWidget);
    expect(find.text(_l10n(tester).untitledConversation), findsNothing);
    expect(_retryButton, findsNothing);
    expect(emitted, isEmpty);
  });

  testWidgets('a row without title or transcript shows a recording date and reports', (tester) async {
    await _pumpRow(
      tester,
      conversation: _conversation(title: '', summaryRetryable: false, segments: const []),
    );

    expect(find.text(_l10n(tester).untitledConversation), findsNothing);
    expect(
      find.text(
        OmiDateFormat.of(
          tester.element(find.byType(ConversationListItem)),
        ).dateTime(DateTime.utc(2020, 1, 1, 12).toLocal()),
      ),
      findsOneWidget,
    );
    expect(emitted, hasLength(1));
    expect(emitted.single.surface, ConversationUntitledRenderedSurface.list);
  });

  testWidgets('a server-titled photo-only row decoded from the API renders its title, not Untitled', (tester) async {
    // The API shape a dead-lettered photo-only row reaches the app with, after the backend
    // resolves a blank user_title override as no override (test_dead_letter_visible_row_title.py).
    final conversation = ServerConversation.fromJson({
      'id': 'photo-only',
      'created_at': '2026-09-30T22:14:00Z',
      'started_at': '2026-09-30T22:14:00Z',
      'finished_at': '2026-09-30T22:20:00Z',
      'structured': {'title': 'Recording · 10:14 PM', 'overview': ''},
      'transcript_segments': <Object>[],
      'status': 'completed',
    });
    await _pumpRow(tester, conversation: conversation);

    expect(find.text('Recording · 10:14 PM'), findsOneWidget);
    expect(find.text(_l10n(tester).untitledConversation), findsNothing);
    expect(emitted, isEmpty);
  });

  testWidgets('Retry shows progress, then a processing result moves the row off the completed list', (tester) async {
    final gate = Completer<ServerConversation?>();
    final provider = await _pumpRow(tester, conversation: _conversation(), reprocess: (_) => gate.future);

    await tester.tap(_retryButton);
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    gate.complete(_conversation(status: ConversationStatus.processing, summaryRetryable: false));
    await tester.pumpAndSettle();

    expect(provider.processingConversations, hasLength(1));
    expect(provider.conversations, isEmpty);
    expect(_indicator, findsNothing);
    expect(find.text('moved-to-processing'), findsOneWidget);

    // A live processing row keeps the provider's periodic reconcile timer
    // armed, and the binding rejects pending timers before addTearDown runs.
    // End the row so the timer cancels within the test body.
    provider.removeProcessingConversation(provider.processingConversations.single.id);
    await tester.pump();
  });

  testWidgets('a successful Retry refreshes the row and clears the chip', (tester) async {
    final provider = await _pumpRow(
      tester,
      conversation: _conversation(),
      reprocess: (_) async => _conversation(title: 'Venue planning', emoji: '📝', summaryRetryable: false),
    );

    await tester.tap(_retryButton);
    await tester.pumpAndSettle();

    expect(provider.conversations.single.structured.title, 'Venue planning');
    expect(provider.conversations.single.summaryRetryable, isFalse);
    expect(find.text('Venue planning'), findsOneWidget);
    expect(_indicator, findsNothing);
    expect(_retryButton, findsNothing);
  });

  testWidgets('a failed Retry keeps the chip and shows an error', (tester) async {
    await _pumpRow(tester, conversation: _conversation(), reprocess: (_) async => null);

    await tester.tap(_retryButton);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(tester.takeException(), isNull);
    expect(_indicator, findsOneWidget);
    expect(_retryButton, findsOneWidget);
    expect(find.text(_l10n(tester).somethingWentWrong), findsOneWidget);
  });

  testWidgets('a thrown Retry error keeps the chip and shows an error', (tester) async {
    await _pumpRow(
      tester,
      conversation: _conversation(),
      reprocess: (_) async {
        throw const FormatException('malformed reprocess body');
      },
    );

    await tester.tap(_retryButton);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(tester.takeException(), isNull);
    expect(_indicator, findsOneWidget);
    expect(find.text(_l10n(tester).somethingWentWrong), findsOneWidget);
  });
}
