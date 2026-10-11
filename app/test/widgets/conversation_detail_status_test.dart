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
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_activity_strip.dart';
import 'package:omi/pages/conversation_detail/widgets/transcript_tab.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';

TranscriptSegment _segment(String text) => TranscriptSegment(
      id: 'seg-1',
      text: text,
      speaker: 'SPEAKER_00',
      isUser: false,
      personId: null,
      start: 0,
      end: 1,
      translations: [],
    );

ServerConversation _conversation({
  List<TranscriptSegment> segments = const [],
  ConversationStatus status = ConversationStatus.completed,
  String overview = '',
}) {
  return ServerConversation(
    id: 'detail-status',
    createdAt: DateTime(2026, 10, 3, 10, 47),
    structured: Structured('Choosing a Table', overview, emoji: '🍽️'),
    transcriptSegments: List.of(segments),
    status: status,
  );
}

ConversationDetailProvider _detail(
  ServerConversation conversation, {
  ConversationDetailFetchCall? fetch,
  ConversationReprocessCall? reprocess,
}) {
  return ConversationDetailProvider(fetchConversation: fetch, reprocess: reprocess)
    ..selectedDate = conversationLocalDayKey(conversation.createdAt)
    ..setCachedConversation(conversation)
    ..titleController = TextEditingController(text: conversation.structured.title)
    ..titleFocusNode = FocusNode();
}

Widget _app(ConversationDetailProvider detail, Widget body) {
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
      ChangeNotifierProvider<PeopleProvider>(create: (_) => PeopleProvider()),
    ],
    child: MaterialApp(
      theme: buildOmiTheme(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: body),
    ),
  );
}

AppLocalizations _l10n(WidgetTester tester) => AppLocalizations.of(tester.element(find.byType(Scaffold)));

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('Transcript tab while its lines are not here yet', () {
    testWidgets('says it is loading, then offers Try Again when the fetch fails, then shows the lines', (tester) async {
      var gate = Completer<ServerConversation?>();
      final detail = _detail(_conversation(), fetch: (_) => gate.future);
      addTearDown(detail.dispose);

      await tester.pumpWidget(_app(detail, const TranscriptWidgets()));
      final l10n = _l10n(tester);

      unawaited(detail.refreshConversation(trackLoad: true));
      await tester.pump();
      expect(find.byKey(const Key('transcript_loading')), findsOneWidget);
      expect(find.text(l10n.loadingTranscript), findsOneWidget);

      gate.complete(null);
      await tester.pump();
      await tester.pump();
      expect(find.byKey(const Key('transcript_loading')), findsNothing);
      expect(find.byKey(const Key('transcript_load_failed')), findsOneWidget);
      expect(find.text(l10n.transcriptLoadFailed), findsOneWidget);

      gate = Completer<ServerConversation?>();
      await tester.tap(find.text(l10n.tryAgain));
      await tester.pump();
      expect(find.byKey(const Key('transcript_loading')), findsOneWidget);

      gate.complete(_conversation(segments: [_segment('Ice? No ice? Yeah.')]));
      await tester.pump();
      await tester.pump();
      expect(find.byKey(const Key('transcript_load_failed')), findsNothing);
      expect(find.byKey(const Key('transcript_loading')), findsNothing);
      expect(find.textContaining('Ice? No ice? Yeah.', findRichText: true), findsWidgets);
    });

    testWidgets('a finished conversation without lines says there is no transcript, not a blank tab', (tester) async {
      final detail = _detail(_conversation());
      addTearDown(detail.dispose);

      await tester.pumpWidget(_app(detail, const TranscriptWidgets()));
      final l10n = _l10n(tester);

      expect(find.byKey(const Key('transcript_empty')), findsOneWidget);
      expect(find.text(l10n.noTranscriptAvailable), findsOneWidget);
    });

    testWidgets('a conversation still processing says so', (tester) async {
      final detail = _detail(_conversation(status: ConversationStatus.processing));
      addTearDown(detail.dispose);

      await tester.pumpWidget(_app(detail, const TranscriptWidgets()));
      expect(find.byKey(const Key('transcript_processing')), findsOneWidget);
      expect(find.text(_l10n(tester).processingConversationProgress), findsOneWidget);
    });

    testWidgets('a conversation the server failed to process offers Try Again, which reprocesses', (tester) async {
      final calls = <String>[];
      final gate = Completer<ServerConversation?>();
      final detail = _detail(
        _conversation(status: ConversationStatus.failed),
        reprocess: (id, {appId, requireSpeakerReceipt = false}) {
          calls.add(id);
          return gate.future;
        },
      );
      addTearDown(detail.dispose);

      await tester.pumpWidget(_app(detail, const TranscriptWidgets()));
      final l10n = _l10n(tester);
      expect(find.byKey(const Key('transcript_processing_failed')), findsOneWidget);
      expect(find.text(l10n.conversationProcessingFailedMessage), findsOneWidget);

      await tester.tap(find.text(l10n.tryAgain));
      await tester.pump();
      expect(calls, ['detail-status']);
      expect(find.byKey(const Key('transcript_processing')), findsOneWidget);
      gate.complete(null);
      await tester.pump();
    });
  });

  group('Activity strip', () {
    testWidgets('shows while this conversation is reprocessed and goes away when it lands', (tester) async {
      final gate = Completer<ServerConversation?>();
      final detail = _detail(
        _conversation(segments: [_segment('Hi')], overview: 'Old summary'),
        reprocess: (id, {appId, requireSpeakerReceipt = false}) => gate.future,
      );
      addTearDown(detail.dispose);

      await tester.pumpWidget(_app(detail, const ConversationActivityStrip()));
      expect(find.byKey(const Key('conversation_activity_strip')), findsNothing);

      unawaited(detail.reprocessConversation());
      await tester.pump();
      expect(find.byKey(const Key('conversation_activity_strip')), findsOneWidget);
      expect(find.text(_l10n(tester).reprocessingConversationProgress), findsOneWidget);
      expect(find.byType(LinearProgressIndicator), findsOneWidget);

      gate.complete(_conversation(segments: [_segment('Hi')], overview: 'New summary'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.byKey(const Key('conversation_activity_strip')), findsNothing);
    });

    testWidgets('while the server is processing, re-reads the conversation until it is done', (tester) async {
      var fetches = 0;
      final detail = _detail(
        _conversation(status: ConversationStatus.processing),
        fetch: (_) async {
          fetches++;
          return _conversation(
            segments: [_segment('Done')],
            status: fetches >= 2 ? ConversationStatus.completed : ConversationStatus.processing,
          );
        },
      );
      addTearDown(detail.dispose);

      await tester.pumpWidget(_app(detail, const ConversationActivityStrip(pollInterval: Duration(seconds: 1))));
      expect(find.text(_l10n(tester).processingConversationProgress), findsOneWidget);

      await tester.pump(const Duration(seconds: 1));
      await tester.pump();
      expect(fetches, 1);
      await tester.pump(const Duration(seconds: 1));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(fetches, 2);
      expect(find.byKey(const Key('conversation_activity_strip')), findsNothing);

      await tester.pump(const Duration(seconds: 3));
      expect(fetches, 2, reason: 'polling stops once the conversation is no longer processing');
    });
  });

  testWidgets('an empty summary under a running reprocess shows progress instead of Generate Summary', (tester) async {
    final gate = Completer<ServerConversation?>();
    final detail = _detail(
      _conversation(segments: [_segment('Hi')]),
      reprocess: (id, {appId, requireSpeakerReceipt = false}) => gate.future,
    );
    addTearDown(detail.dispose);

    await tester.pumpWidget(_app(detail, const CustomScrollView(slivers: [GetAppsWidgets()])));
    final l10n = _l10n(tester);
    expect(find.text(l10n.generateSummary), findsOneWidget);

    unawaited(detail.reprocessConversation());
    await tester.pump();
    expect(find.text(l10n.generateSummary), findsNothing);
    expect(find.text(l10n.summarizingConversation), findsOneWidget);

    gate.complete(null);
    await tester.pump();
  });

  group('Stale reads and other conversations', () {
    testWidgets('a slower, older read never replaces a newer one', (tester) async {
      final reads = <Completer<ServerConversation?>>[];
      final detail = _detail(
        _conversation(status: ConversationStatus.processing),
        fetch: (_) {
          final read = Completer<ServerConversation?>();
          reads.add(read);
          return read.future;
        },
      );
      addTearDown(detail.dispose);

      final older = detail.refreshConversation();
      final newer = detail.refreshConversation();
      reads[1].complete(_conversation(segments: [_segment('Done')], overview: 'Final summary'));
      await newer;
      reads[0].complete(_conversation(status: ConversationStatus.processing));
      await older;

      expect(detail.conversation.status, ConversationStatus.completed);
      expect(detail.conversation.structured.overview, 'Final summary');
    });

    testWidgets("the previous conversation's late failure does not mark this one failed", (tester) async {
      final reads = <String, Completer<ServerConversation?>>{};
      final detail = _detail(
        _conversation(),
        fetch: (id) {
          final read = Completer<ServerConversation?>();
          reads[id] = read;
          return read.future;
        },
      );
      addTearDown(detail.dispose);

      final first = detail.refreshConversation(trackLoad: true);
      final other = ServerConversation(
        id: 'other',
        createdAt: DateTime(2026, 10, 3, 12),
        structured: Structured('Other', ''),
        transcriptSegments: [],
      );
      detail.setCachedConversation(other);
      final second = detail.refreshConversation(trackLoad: true);
      expect(detail.detailLoad, ConversationDetailLoad.loading);

      reads['detail-status']!.complete(null);
      await first;
      expect(
        detail.detailLoad,
        ConversationDetailLoad.loading,
        reason: "the first conversation's failure belongs to the first conversation",
      );

      reads['other']!.complete(other);
      await second;
      expect(detail.detailLoad, ConversationDetailLoad.idle);
    });

    testWidgets('a failed reprocess remembers which conversation failed', (tester) async {
      final gate = Completer<ServerConversation?>();
      final detail = _detail(
        _conversation(segments: [_segment('Hi')]),
        reprocess: (id, {appId, requireSpeakerReceipt = false}) => gate.future,
      );
      addTearDown(detail.dispose);

      final run = detail.reprocessConversation();
      detail.setCachedConversation(
        ServerConversation(
          id: 'opened-later',
          createdAt: DateTime(2026, 10, 3, 12),
          structured: Structured('Other', ''),
          transcriptSegments: [],
        ),
      );
      gate.complete(null);
      await run;

      expect(detail.lastFailedReprocessConversationId, 'detail-status');
      expect(
        detail.lastFailedReprocessConversationId,
        isNot(detail.conversation.id),
        reason: 'the page compares this to the open conversation before offering Try Again',
      );
    });
  });
}
