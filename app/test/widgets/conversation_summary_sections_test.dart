import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/utils/audio/conversation_playback_controller.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_summary_selection.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/providers/conversation_provider.dart';

ServerConversation _conversationWithSections(
    {List<AppResponse> appResults = const [],
    String overview = '',
    List<TranscriptSegment> transcriptSegments = const []}) {
  final structured = Structured('Sprint sync', overview, emoji: '🧠');
  structured.sections = [
    const wire.GeneratedSection(heading: 'Decisions', bodyMarkdown: 'Ship the beta on Friday'),
    const wire.GeneratedSection(heading: 'Risks', bodyMarkdown: 'Backend migration is not started yet'),
  ];
  return ServerConversation(
    id: 'conv-1',
    createdAt: DateTime(2026, 7, 1, 9).toUtc(),
    structured: structured,
    appResults: appResults,
    transcriptSegments: transcriptSegments,
  );
}

Future<void> _pumpSummary(
  WidgetTester tester,
  ServerConversation conversation, {
  bool asSliver = true,
  ValueChanged<String>? onOpenSource,
  void Function(ConversationSummarySelection selection, String newContent)? onSaveSummarySelection,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.dark(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: asSliver
            ? CustomScrollView(
                slivers: [
                  AppResultDetailWidget(
                    summarySelection: ConversationSummarySelection.select(conversation),
                    app: null,
                    conversation: conversation,
                    onSaveSummarySelection: onSaveSummarySelection,
                    asSliver: true,
                    onOpenSource: onOpenSource,
                  ),
                ],
              )
            : AppResultDetailWidget(
                summarySelection: ConversationSummarySelection.select(conversation),
                app: null,
                conversation: conversation,
                onSaveSummarySelection: onSaveSummarySelection,
              ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  TranscriptSegment segment(String id, double start, [String text = 'Evidence']) => TranscriptSegment(
      id: id, text: text, speaker: null, isUser: false, personId: null, start: start, end: start + 1, translations: []);

  Future<void> openSources(WidgetTester tester, {int index = 0}) async {
    await tester.tap(find.byKey(const ValueKey('section-sources')).at(index));
    await tester.pumpAndSettle();
  }

  testWidgets('sources stay out of the prose and open per section in a sheet', (tester) async {
    final semantics = tester.ensureSemantics();
    final starts = [42.9, 312.0, 460.0, 3912.0, 3600.0];
    final conversation = _conversationWithSections(transcriptSegments: [
      for (var i = 0; i < starts.length; i++) segment('s$i', starts[i], 'Source $i'),
    ]);
    conversation.structured.sections = [
      for (final heading in ['Main', 'Other'])
        Section(
            heading: heading, bodyMarkdown: 'Body', sourceSegmentIds: ['missing', 's0', 's1', 's2', 's3', 's4', 's0']),
    ];
    final opened = <String>[];
    await _pumpSummary(tester, conversation, onOpenSource: opened.add);
    expect(find.text('0:42'), findsNothing);
    expect(find.byKey(const ValueKey('section-sources')), findsNWidgets(2));
    expect(find.bySemanticsLabel('Show sources'), findsNWidgets(2));

    await openSources(tester, index: 1);
    expect(find.text('Other'), findsNWidgets(2));
    for (final time in ['0:42', '5:12', '7:40', '1:05:12', '1:00:00']) {
      expect(find.text(time), findsOneWidget);
    }
    expect(find.text('Source 3'), findsOneWidget);
    expect(find.byKey(const ValueKey('section-source-missing')), findsNothing);
    expect(find.bySemanticsLabel('Jump to 5 mins 12 secs'), findsOneWidget);
    await tester.tap(find.text('1:05:12'));
    await tester.pumpAndSettle();
    expect(opened, ['s3']);
    expect(find.text('Source 3'), findsNothing);
    semantics.dispose();
  });

  testWidgets('a heading-less section with sources still gets its control', (tester) async {
    final conversation = _conversationWithSections(transcriptSegments: [segment('s1', 42)]);
    conversation.structured.sections = [
      const Section(heading: '', bodyMarkdown: 'Body only', sourceSegmentIds: ['s1']),
      const Section(heading: '', bodyMarkdown: 'Unsourced body'),
    ];
    final opened = <String>[];
    await _pumpSummary(tester, conversation, onOpenSource: opened.add);
    expect(find.byKey(const ValueKey('section-sources')), findsOneWidget);
    await openSources(tester);
    await tester.tap(find.byKey(const ValueKey('section-source-s1')));
    await tester.pumpAndSettle();
    expect(opened, ['s1']);
  });

  testWidgets('the sources control answers a single tap at once on an editable summary', (tester) async {
    final conversation = _conversationWithSections(transcriptSegments: [segment('s1', 42)]);
    conversation.structured.sections = [
      const Section(heading: 'Decisions', bodyMarkdown: 'Body', sourceSegmentIds: ['s1']),
    ];
    await _pumpSummary(tester, conversation, onOpenSource: (_) {}, onSaveSummarySelection: (_, __) {});
    await tester.tap(find.byKey(const ValueKey('section-sources')));
    // Well inside the 300ms double-tap timeout: a double-tap ancestor would still hold the tap.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.byKey(const ValueKey('section-source-s1')), findsOneWidget);
    await tester.pumpAndSettle();
  });

  testWidgets('unresolvable sources render no sources control', (tester) async {
    final conversation = _conversationWithSections();
    conversation.structured.sections = [
      const Section(heading: 'Missing', bodyMarkdown: 'Body', sourceSegmentIds: ['missing']),
    ];
    await _pumpSummary(tester, conversation, onOpenSource: (_) => fail('No source should open'));
    expect(find.text('Missing'), findsOneWidget);
    expect(find.byKey(const ValueKey('section-sources')), findsNothing);
  });

  testWidgets('an absent transcript ID cannot resolve an empty source ID', (tester) async {
    final empty = TranscriptSegment.fromJson({
      'text': 'Missing identity',
      'is_user': false,
      'start': 42.0,
      'end': 43.0,
    });
    expect(empty.id, '');
    final conversation = _conversationWithSections(transcriptSegments: [empty]);
    conversation.structured.sections = [
      const Section(heading: 'Missing', bodyMarkdown: 'Body', sourceSegmentIds: ['']),
    ];
    await _pumpSummary(tester, conversation, onOpenSource: (_) => fail('No source should open'));
    expect(find.byKey(const ValueKey('section-sources')), findsNothing);
    expect(find.text('0:42'), findsNothing);
  });

  testWidgets('hour timestamps speak singular hours and seconds precisely', (tester) async {
    final semantics = tester.ensureSemantics();
    try {
      final conversation = _conversationWithSections(transcriptSegments: [
        for (final start in [3600.0, 3601.0]) segment('$start', start),
      ]);
      conversation.structured.sections = [
        const Section(heading: 'Hour', bodyMarkdown: 'Body', sourceSegmentIds: ['3600.0', '3601.0']),
      ];
      await _pumpSummary(tester, conversation, onOpenSource: (_) {});
      await openSources(tester);
      expect(find.text('1:00:00'), findsOneWidget);
      expect(find.text('1:00:01'), findsOneWidget);
      expect(find.bySemanticsLabel('Jump to 1 hour, 0 mins, 0 secs'), findsOneWidget);
      expect(find.bySemanticsLabel('Jump to 1 hour, 0 mins, 1 sec'), findsOneWidget);
    } finally {
      semantics.dispose();
    }
  });

  testWidgets('typed section sources navigate and highlight through the existing transcript controller',
      (tester) async {
    final conversation = _conversationWithSections(transcriptSegments: [segment('s1', 3, 'Approved')]);
    conversation.structured.sections = [
      const Section(heading: 'Decision []', bodyMarkdown: 'Approved. [s1]', sourceSegmentIds: ['missing', 's1', 's1']),
      const Section(heading: 'Legacy', bodyMarkdown: 'No typed sources. [s1] []'),
    ];
    final selection = ConversationSummarySelection.select(conversation);
    expect(selection.sections[0].sourceSegmentIds, ['s1']);
    // The legacy section's only evidence was the inline citation the repair removed; it stays its source.
    expect(selection.sections[1].sourceSegmentIds, ['s1']);
    final controller = ConversationPlaybackController(segments: conversation.transcriptSegments);
    addTearDown(controller.dispose);
    await _pumpSummary(tester, conversation, onOpenSource: (id) {
      final segment = conversation.transcriptSegments.singleWhere((segment) => segment.id == id);
      controller.seek(segment.start, strict: true);
    });
    expect(find.byKey(const ValueKey('section-sources')), findsNWidgets(2));
    await openSources(tester);
    expect(find.byKey(const ValueKey('section-source-s1')), findsOneWidget);
    expect(find.byKey(const ValueKey('section-source-missing')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('section-source-s1')));
    await tester.pumpAndSettle();
    expect(controller.highlightedSegment.value, 's1');
    expect(controller.followTargetSegmentId, 's1');
    expect(controller.followRequest, 1);
    expect(controller.isPlaying, isFalse);
    expect(conversation.structured.sections.first.heading, 'Decision []');
  });

  testWidgets('section presentation still edits the entire selected summary', (tester) async {
    final conversation = _conversationWithSections();
    await _pumpSummary(tester, conversation, onSaveSummarySelection: (_, __) {});
    final body = find.textContaining('Ship the beta on Friday', findRichText: true);
    await tester.tap(body);
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(body);
    await tester.pump();
    expect(find.byType(TextField), findsOneWidget);
    final editor = tester.widget<TextField>(find.byType(TextField));
    expect(editor.controller!.text, ConversationSummarySelection.select(conversation).content);
    expect(editor.controller!.text, contains('Risks'));
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 1));
  });

  group('renderSections', () {
    test('renders each section as a heading followed by its markdown body', () {
      final markdown = ConversationSummarySelection.renderSections(const [
        wire.GeneratedSection(heading: 'Decisions', bodyMarkdown: '- Ship on Friday'),
        wire.GeneratedSection(heading: 'Risks', bodyMarkdown: 'Migration pending'),
      ]);

      expect(markdown, '## Decisions\n\n- Ship on Friday\n\n## Risks\n\nMigration pending');
    });

    test('skips fully empty sections', () {
      final markdown = ConversationSummarySelection.renderSections(const [
        wire.GeneratedSection(heading: '  ', bodyMarkdown: ''),
        wire.GeneratedSection(heading: 'Kept', bodyMarkdown: 'Body'),
      ]);

      expect(markdown, '## Kept\n\nBody');
    });

    test('ignores heading-only sections and keeps body-only sections', () {
      final markdown = ConversationSummarySelection.renderSections(const [
        wire.GeneratedSection(heading: 'Unused', bodyMarkdown: ' '),
        wire.GeneratedSection(heading: '', bodyMarkdown: 'Body only'),
      ]);

      expect(markdown, 'Body only');
    });
  });

  group('conversation summary sections rendering', () {
    testWidgets('renders the projected overview once when it duplicates sections', (tester) async {
      final conversation = _conversationWithSections();
      conversation.structured.overview = ConversationSummarySelection.renderSections(conversation.structured.sections);

      await _pumpSummary(tester, conversation);

      expect(find.textContaining('Decisions', findRichText: true), findsOneWidget);
      expect(find.textContaining('Ship the beta on Friday', findRichText: true), findsOneWidget);
      expect(find.textContaining('Risks', findRichText: true), findsOneWidget);
      expect(find.textContaining('Backend migration is not started yet', findRichText: true), findsOneWidget);
    });

    testWidgets('regular rendering also mounts the selected body once', (tester) async {
      final conversation = _conversationWithSections();
      conversation.structured.overview = ConversationSummarySelection.renderSections(conversation.structured.sections);

      await _pumpSummary(tester, conversation, asSliver: false);

      expect(find.textContaining('Decisions', findRichText: true), findsOneWidget);
      expect(find.textContaining('Ship the beta on Friday', findRichText: true), findsOneWidget);
      expect(find.textContaining('Risks', findRichText: true), findsOneWidget);
      expect(find.textContaining('Backend migration is not started yet', findRichText: true), findsOneWidget);
    });

    testWidgets('an app-generated summary replaces the structured sections', (tester) async {
      final conversation = _conversationWithSections(appResults: [AppResponse('App summary', appId: 'app-1')]);

      await _pumpSummary(tester, conversation);

      expect(find.textContaining('App summary', findRichText: true), findsOneWidget);
      expect(find.textContaining('Decisions', findRichText: true), findsNothing);
    });

    testWidgets('an app result with empty content falls back to the overview or sections once', (tester) async {
      // End of the regression this pane actually showed: the provider handed
      // over an empty-content app result, its non-null appId suppressed the
      // sections, and the empty content selected the "no summary" placeholder.
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();

      final conversation = _conversationWithSections(
        overview: '',
        appResults: [AppResponse('', appId: 'app-1')],
      );

      final provider = ConversationDetailProvider();
      addTearDown(provider.dispose);
      provider.selectedDate = conversationLocalDayKey(conversation.createdAt);
      provider.setCachedConversation(conversation);

      await _pumpSummary(tester, conversation);

      expect(find.textContaining('Decisions', findRichText: true), findsOneWidget);
      expect(find.textContaining('Ship the beta on Friday', findRichText: true), findsOneWidget);
      expect(find.textContaining('No summary available for this app', findRichText: true), findsNothing);
    });

    testWidgets('duplicate app ids disable editing in regular and sliver rendering', (tester) async {
      final conversation = _conversationWithSections(
        appResults: [
          AppResponse('First app summary', appId: 'duplicate'),
          AppResponse('Second app summary', appId: 'duplicate'),
        ],
      );
      var saveCalls = 0;
      void onSave(ConversationSummarySelection selection, String newContent) {
        saveCalls++;
      }

      await _pumpSummary(tester, conversation, onSaveSummarySelection: onSave);
      final summaryFinder = find.textContaining('First app summary', findRichText: true);
      await tester.tap(summaryFinder);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(summaryFinder);
      await tester.pump();
      expect(find.byType(TextField), findsNothing);

      await _pumpSummary(tester, conversation, asSliver: false, onSaveSummarySelection: onSave);
      await tester.tap(summaryFinder);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(summaryFinder);
      await tester.pump();
      expect(find.byType(TextField), findsNothing);
      expect(saveCalls, 0);
    });
  });
}
