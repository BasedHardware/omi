import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/interim_summary.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets/quick_summary_card.dart';
import 'package:omi/services/experiments/quick_summary_gate.dart';

ServerConversation _conversation(String id) => ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026),
      structured: Structured('', ''),
      status: ConversationStatus.processing,
    );

Widget _host(List<Widget> slivers) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: CustomScrollView(slivers: slivers)),
    );

void main() {
  setUp(QuickSummarySliver.debugClearCache);

  test('parses SSE data lines into events and skips noise', () async {
    final body = [
      'data: {"type": "start", "model": "gpt-5-nano"}',
      ': keep-alive',
      'data: {"type": "delta", "text": "# Launch"}',
      'data: {"type": "unknown"}',
      'data: {"type": "done", "ttft_s": 0.8, "total_s": 1.2, "usd": 0.00003}',
      '',
    ].join('\n');
    final events = await parseInterimSummaryStream(Stream.value(utf8.encode(body))).toList();
    expect(events, hasLength(3));
    expect(events[1], isA<InterimSummaryDelta>().having((e) => e.text, 'text', '# Launch'));
    expect(events[2], isA<InterimSummaryDone>());
  });

  test('a malformed data line is a decode failure, not silence', () async {
    final body = 'data: {"type": "delta", "text": "# Launch"}\ndata: not json\n';
    final stream = parseInterimSummaryStream(Stream.value(utf8.encode(body)));
    await expectLater(stream, emitsInOrder([isA<InterimSummaryDelta>(), emitsError(isA<FormatException>())]));
  });

  test('splits the streamed Markdown into a title and note sections', () {
    final parsed = parseQuickSummary('# Launch moved\n\n## Launch date\n- Now Thursday the 20th\n'
        '- Budget stays \$8,000\n\n## Next steps\n- Daniel drafts the email');
    expect(parsed.title, 'Launch moved');
    expect(parsed.sections.map((s) => s.heading), ['Launch date', 'Next steps']);
    expect(parsed.sections.first.bodyMarkdown, '- Now Thursday the 20th\n- Budget stays \$8,000');

    final early = parseQuickSummary('# Launch moved\n## Launch da');
    expect(early.sections.single.heading, 'Launch da', reason: 'a heading streams in as it is written');
    expect(parseQuickSummary('Just a sentence.').sections.single.heading, '');
  });

  testWidgets('streams in the notes layout, publishes its title, and keeps the full summary pending', (tester) async {
    final events = StreamController<InterimSummaryEvent>();
    var polls = 0;
    await tester.pumpWidget(_host([
      QuickSummarySliver(
          conversation: _conversation('c1'), streamSummary: () => events.stream, onPoll: () async => polls++),
    ]));
    expect(find.text('Quick Summary'), findsNothing, reason: 'no separate card label: it looks like the notes');
    expect(find.text('Writing the full summary…'), findsOneWidget);

    events.add(const InterimSummaryDelta('# Launch moved\n\n## Launch date\n- Now Thursday the 20th\n'));
    events.add(const InterimSummaryDone(ttftSeconds: 0.8, totalSeconds: 1.2));
    await tester.pump();
    expect(find.text('Launch date'), findsOneWidget);
    expect(find.textContaining('Now Thursday the 20th', findRichText: true), findsOneWidget);
    expect(find.text('Launch moved'), findsNothing, reason: 'the title belongs in the page header');
    expect(QuickSummarySliver.titles.value['c1'], 'Launch moved');
    expect(find.textContaining('first words'), findsNothing, reason: 'no timings shown');

    await tester.pump(const Duration(seconds: 3));
    await tester.pump(const Duration(seconds: 3));
    expect(polls, 2, reason: 'asks the page to refresh until the full summary lands');
    await events.close();
  });

  testWidgets('a reopened page reuses the written Quick Summary instead of paying again', (tester) async {
    var streams = 0;
    Stream<InterimSummaryEvent> stream() {
      streams++;
      return Stream.fromIterable(const [InterimSummaryDelta('# Same\n## Same summary\n- point'), InterimSummaryDone()]);
    }

    await tester.pumpWidget(_host([QuickSummarySliver(conversation: _conversation('c2'), streamSummary: stream)]));
    await tester.pump();
    await tester.pumpWidget(const SizedBox());
    await tester.pumpWidget(_host([QuickSummarySliver(conversation: _conversation('c2'), streamSummary: stream)]));
    await tester.pump();
    expect(streams, 1);
    expect(find.text('Same summary'), findsOneWidget);
  });

  testWidgets('an error shows only that the full summary is coming', (tester) async {
    await tester.pumpWidget(_host([
      QuickSummarySliver(
        conversation: _conversation('c3'),
        streamSummary: () => Stream.value(const InterimSummaryError('HTTP 503')),
      ),
    ]));
    await tester.pump();
    expect(find.text('Writing the full summary…'), findsOneWidget);
    expect(QuickSummarySliver.takeHandoff('c3'), isFalse, reason: 'nothing was shown to fade over');
  });

  testWidgets('a transport or decode failure shows the same fallback', (tester) async {
    await tester.pumpWidget(_host([
      QuickSummarySliver(
        conversation: _conversation('c3e'),
        streamSummary: () => Stream.error(const FormatException('bad payload')),
      ),
    ]));
    await tester.pump();
    expect(find.text('Writing the full summary…'), findsOneWidget);
    expect(QuickSummarySliver.takeHandoff('c3e'), isFalse);
  });

  testWidgets('the full summary fades in once after a Quick Summary, and not on later opens', (tester) async {
    await tester.pumpWidget(_host([
      QuickSummarySliver(
        conversation: _conversation('c4'),
        streamSummary: () =>
            Stream.fromIterable(const [InterimSummaryDelta('## Topic\n- point'), InterimSummaryDone()]),
      ),
    ]));
    await tester.pump();

    const full = SliverToBoxAdapter(child: Text('Full summary'));
    double opacity() => tester.widget<SliverFadeTransition>(find.byType(SliverFadeTransition)).opacity.value;
    await tester.pumpWidget(_host([const QuickSummaryHandoff(conversationId: 'c4', sliver: full)]));
    expect(opacity(), 0);
    await tester.pumpAndSettle();
    expect(opacity(), 1);

    await tester.pumpWidget(const SizedBox());
    await tester.pumpWidget(_host([const QuickSummaryHandoff(conversationId: 'c4', sliver: full)]));
    expect(opacity(), 1, reason: 'a later open shows the summary at once');
  });

  test('is off by default', () => expect(QuickSummaryGate.isEnabled, isFalse));
}
