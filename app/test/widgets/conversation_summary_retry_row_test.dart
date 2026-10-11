import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/conversations/conversation_title.dart';
import 'package:omi/ui/format/omi_date_format.dart';

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
                reprocess: reprocess,
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
