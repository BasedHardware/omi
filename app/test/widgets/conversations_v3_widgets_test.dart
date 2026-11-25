import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations_v3.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversations/widgets/live_conversation_end_button.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/live_conversation_refresher.dart';
import 'package:omi/pages/conversation_detail/widgets/live_summary_section.dart';
import 'package:omi/pages/conversations/widgets/conversation_state_tile.dart';
import 'package:omi/pages/conversations/widgets/day_summary_link.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import '../helpers/sfpro_font_fixtures.dart';

String _testRecapInterval() => 'deafbee0-0000-4000-8000-000000000000';

ServerConversation _conversation({
  ConversationTileState? state,
  DateTime? covers,
  DateTime? latestSpeech,
  String overview = '',
  String? speech,
}) =>
    ServerConversation(
      id: 'c1',
      createdAt: DateTime(2026, 11, 16, 9),
      startedAt: DateTime(2026, 11, 16, 9),
      finishedAt: latestSpeech,
      structured: Structured('Planning the launch', overview, emoji: '🚀', category: 'work'),
      transcriptSegments: speech == null
          ? []
          : [
              TranscriptSegment(
                  id: 'speech',
                  text: speech,
                  speaker: 'SPEAKER_00',
                  personId: null,
                  isUser: true,
                  start: 0,
                  end: 10,
                  translations: [])
            ],
      v3: state == null && covers == null
          ? null
          : ConversationV3Fields(kind: 'conversation', tileState: state, summaryCoversThrough: covers),
    );

ConversationsV3Provider _v3(bool on) => ConversationsV3Provider(
    fetchLive: () async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    uid: () => 'u1',
    cached: 'u1:${on ? 1 : 0}');

Widget _wrap(Widget child) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Scaffold(body: child),
    );

Widget _sliver(Widget sliver) => _wrap(CustomScrollView(slivers: [sliver]));

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'fixture-user'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  group('ConversationStateTile', () {
    Future<void> pumpTile(WidgetTester tester, ServerConversation c, {ConversationsV3Provider? v3}) async {
      await tester.pumpWidget(ChangeNotifierProvider<ConversationsV3Provider>.value(
        value: v3 ?? _v3(true),
        child: _wrap(Center(child: ConversationStateTile(conversation: c))),
      ));
      await tester.pump();
    }

    testWidgets('a conversation in progress breathes', (tester) async {
      await pumpTile(tester, _conversation(state: ConversationTileState.live));
      expect(find.byKey(const Key('conversation_tile_live')), findsOneWidget);
      expect(find.byType(OmiBreathingDot), findsOneWidget);
      expect(find.text('🚀'), findsNothing);
    });

    testWidgets('transcribing spins', (tester) async {
      await pumpTile(tester, _conversation(state: ConversationTileState.transcribing));
      expect(find.byKey(const Key('conversation_tile_transcribing')), findsOneWidget);
    });

    testWidgets('writing shows the pen', (tester) async {
      await pumpTile(tester, _conversation(state: ConversationTileState.writing));
      expect(find.byKey(const Key('conversation_tile_writing')), findsOneWidget);
      expect(find.byIcon(Icons.edit_rounded), findsOneWidget);
    });

    testWidgets('an account not on v3 shows the emoji, whatever an old document says', (tester) async {
      await pumpTile(tester, _conversation(state: ConversationTileState.writing), v3: _v3(false));
      expect(find.text('🚀'), findsOneWidget);
      expect(find.byType(ConversationWritingPen), findsNothing);
    });

    testWidgets('failed shows a warning mark, never the emoji', (tester) async {
      await pumpTile(tester, _conversation(state: ConversationTileState.failed));
      expect(find.byKey(const Key('conversation_tile_failed')), findsOneWidget);
      expect(find.text('🚀'), findsNothing);
      expect(find.bySemanticsLabel('Summary failed'), findsOneWidget);
    });

    testWidgets('done, and every conversation without v3 fields, shows its emoji', (tester) async {
      await pumpTile(tester, _conversation(state: ConversationTileState.done));
      expect(find.text('🚀'), findsOneWidget);
      await pumpTile(tester, _conversation());
      expect(find.text('🚀'), findsOneWidget);
    });
  });

  group('DaySummaryHeader', () {
    testWidgets('a finished day opens its summary', (tester) async {
      final asked = <String>[];
      final opened = <DailySummary>[];
      final summary = DailySummary.fromJson({
        'id': 's1',
        'date': '2026-11-15',
        'created_at': '2026-11-16T01:00:00Z',
        'headline': 'A day of planning',
        'overview': 'You planned the launch.',
        'day_emoji': '🗓️',
        'stats': <String, dynamic>{},
        'highlights': <Object>[],
        'action_items': <Object>[],
      });
      await tester.pumpWidget(_wrap(DaySummaryHeader(
        date: DateTime(2026, 11, 15),
        isFirst: false,
        open: (date) async {
          asked.add(date);
          return ApiSuccess(summary);
        },
        onOpened: opened.add,
      )));
      expect(find.byIcon(Icons.chevron_right_rounded), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('day_summary_header_2026-11-15')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump(const Duration(seconds: 1));
      expect(asked, ['2026-11-15']);
      expect(opened.single.id, 's1');
    });

    testWidgets('a failure says why and stays put', (tester) async {
      await tester.pumpWidget(_wrap(DaySummaryHeader(
        date: DateTime(2026, 11, 15),
        isFirst: true,
        open: (_) async => const ApiFailure(ApiProblem(ApiProblemKind.server, statusCode: 400)),
      )));
      expect(tester.getSize(find.byType(InkWell)).height, greaterThanOrEqualTo(44));
      await tester.tap(find.byType(InkWell));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.byType(DaySummaryHeader), findsOneWidget);
      expect(find.byIcon(Icons.chevron_right_rounded), findsOneWidget, reason: 'the spinner is gone');
      final l10n = lookupAppLocalizations(const Locale('en'));
      expect(find.text(l10n.recapRegenerateNoConversations), findsOneWidget);
    });

    testWidgets('failure copy matches the recap recovery action', (tester) async {
      late BuildContext context;
      await tester.pumpWidget(_wrap(Builder(builder: (c) {
        context = c;
        return const SizedBox();
      })));
      final l10n = lookupAppLocalizations(const Locale('en'));
      String message(ApiProblem p) => daySummaryFailureMessage(context, p);
      expect(message(const ApiProblem(ApiProblemKind.server, statusCode: 402)), l10n.upgradePlan);
      expect(message(const ApiProblem(ApiProblemKind.server, statusCode: 422)), l10n.trySelectingDifferentDate);
      expect(message(const ApiProblem(ApiProblemKind.server, statusCode: 429)), l10n.recapRegenerateCooldown);
      expect(message(const ApiProblem(ApiProblemKind.authTerminal)), l10n.sessionExpiredSignInAgain);
      expect(message(const ApiProblem(ApiProblemKind.transport)), l10n.checkConnectionTryAgain);
    });
  });

  test('ownsCapture detects overlapping locally received segment IDs', () {
    ServerConversation window(List<String> ids) => ServerConversation(
          id: 'w1',
          createdAt: DateTime(2026, 11, 16, 9),
          structured: Structured('', ''),
          transcriptSegments: [
            for (final id in ids)
              TranscriptSegment(
                  id: id,
                  text: 'x',
                  speaker: 'SPEAKER_00',
                  isUser: true,
                  personId: null,
                  start: 0,
                  end: 1,
                  translations: []),
          ],
        );
    expect(LiveConversationEndButton.ownsCapture(window(['a', 'b']), ['b', 'z']), isTrue);
    expect(LiveConversationEndButton.ownsCapture(window(['a', 'b']), ['z']), isFalse,
        reason: "another device's window");
    expect(LiveConversationEndButton.ownsCapture(window([]), ['z']), isFalse, reason: 'transcript not loaded yet');
    expect(LiveConversationEndButton.ownsCapture(window(['a']), const []), isFalse, reason: 'nothing captured here');
  });

  group('LiveSummarySection', () {
    const output = String.fromEnvironment('V3_LIVE_CATCHUP_RENDER_OUTPUT');
    final capture = GlobalKey();
    final enoughSpeech = List.filled(300, 'word').join(' ');

    setUpAll(() async {
      if (output.isEmpty) return;
      final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
      for (final family in manifest) {
        final loader = FontLoader(family['family'] as String);
        for (final font in family['fonts'] as List) {
          loader.addFont(rootBundle.load(font['asset'] as String));
        }
        await loader.load();
      }
      for (final fontFamily in [
        '.SF UI Text',
        '.SF UI Display',
        '.SF Pro Display',
        'SF Pro Display',
        'CupertinoSystemText',
        'CupertinoSystemDisplay',
        'FlutterTest',
        'Roboto'
      ]) {
        final loader = FontLoader(fontFamily);
        for (final style in ['REGULAR', 'MEDIUM', 'BOLD']) {
          loader.addFont(sfProFont('SFPRODISPLAY$style.OTF'));
        }
        await loader.load();
      }
      OmiColors.active = OmiColors.forBrightness(Brightness.light);
    });

    Widget liveSnapshot(LiveSummarySection section) => MaterialApp(
          theme: buildOmiTheme(brightness: Brightness.light),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Scaffold(
            body: RepaintBoundary(
              key: capture,
              child: ColoredBox(
                color: Colors.white,
                child: CustomScrollView(
                  slivers: [SliverPadding(padding: const EdgeInsets.all(24), sliver: section)],
                ),
              ),
            ),
          ),
        );

    Future<void> shoot(WidgetTester tester, String name) async {
      if (output.isEmpty) return;
      await tester.runAsync(() async {
        final render = capture.currentContext!.findRenderObject()! as RenderRepaintBoundary;
        final image = await render.toImage(pixelRatio: 3);
        final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
        await Directory(output).create(recursive: true);
        await File('$output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
        image.dispose();
      });
    }

    testWidgets('saved recap refreshes on a viewing interval and retains streamed coverage', (tester) async {
      final events = StreamController<SummaryStreamEvent>();
      var opens = 0;
      var refreshes = 0;
      final through = DateTime(2026, 11, 16, 9, 20);
      final conversation = ServerConversation.fromJson({
        ..._conversation(state: ConversationTileState.live, latestSpeech: through, speech: enoughSpeech).toJson(),
        'live_summary': {
          'structured': {'title': 'Launch', 'overview': 'We agreed on the launch plan.'},
          'summary_covers_through': through.subtract(const Duration(minutes: 3)).toIso8601String(),
        },
      });
      expect(conversation.v3!.summaryCoversThrough, isNull);
      expect(conversation.toJson().containsKey('live_summary'), isFalse);
      tester.view.physicalSize = const Size(390, 500);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      conversation.transcriptSegments.add(TranscriptSegment(
        id: 'append',
        text: 'New speech.',
        start: 1190,
        end: 1200,
        speaker: 'SPEAKER_00',
        personId: null,
        isUser: true,
        translations: [],
      ));
      Future<void> show(int tick) => tester.pumpWidget(liveSnapshot(LiveSummarySection(
            liveInterval: _testRecapInterval,
            refreshTick: tick,
            conversation: conversation,
            open: 1,
            stream: (_) {
              opens++;
              return events.stream;
            },
            refresh: () async {
              refreshes++;
              return false;
            },
            onActiveChanged: (_) {},
          )));
      await show(0);
      await tester.pump();
      expect(opens, 0);
      expect(find.textContaining('Summary through'), findsOneWidget);
      expect(find.textContaining('We agreed on the launch plan.'), findsOneWidget);
      final action = find.byKey(const Key('live_summary_catch_up'));
      expect(action, findsNothing);
      await shoot(tester, '01-live-summary-catch-up');

      await show(1);
      await tester.pump();
      await tester.pump();
      expect(opens, 1);
      expect(action, findsNothing);
      expect(find.text('Writing your summary…'), findsOneWidget);
      events.add(const SummarySection('## Launch\n- We confirmed Thursday.'));
      await tester.pump();
      expect(find.textContaining('We confirmed Thursday.'), findsOneWidget);
      events.add(SummaryDone(Structured('Launch', 'We confirmed Thursday.'), through));
      await tester.pump();
      expect(find.textContaining('We confirmed Thursday.'), findsOneWidget);
      expect(find.textContaining('Summary through'), findsOneWidget);
      expect(find.text('Writing your summary…'), findsNothing);
      expect(action, findsNothing);
      await show(2);
      await tester.pump();
      expect(opens, 1, reason: 'no new speech since the prior generation');
      expect(refreshes, 0, reason: 'the terminal stream frame already contains the body and coverage');
      expect(opens, 1);
      await shoot(tester, '02-live-summary-current-coverage');
      await tester.pumpWidget(const SizedBox());
      unawaited(events.close());
    });

    testWidgets('disposing Summary cancels the in-flight live recap subscription', (tester) async {
      var canceled = false;
      final events = StreamController<SummaryStreamEvent>(onCancel: () => canceled = true);
      await tester.pumpWidget(liveSnapshot(LiveSummarySection(
        conversation: _conversation(state: ConversationTileState.live, speech: enoughSpeech),
        liveInterval: _testRecapInterval,
        open: 1,
        stream: (_) => events.stream,
        refresh: () async => false,
        onActiveChanged: (_) {},
      )));
      await tester.pump();
      expect(events.hasListener, isTrue);
      await tester.pumpWidget(const SizedBox());
      expect(canceled, isTrue);
      unawaited(events.close());
    });

    testWidgets('leaving the foreground immediately cancels an active live recap', (tester) async {
      final events = StreamController<SummaryStreamEvent>();
      await tester.pumpWidget(liveSnapshot(LiveSummarySection(
        conversation: _conversation(state: ConversationTileState.live, speech: enoughSpeech),
        liveInterval: _testRecapInterval,
        open: 1,
        stream: (_) => events.stream,
        refresh: () async => false,
        onActiveChanged: (_) {},
      )));
      await tester.pump();
      expect(events.hasListener, isTrue);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      expect(events.hasListener, isFalse);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      expect(events.hasListener, isFalse);
      await tester.pumpWidget(const SizedBox());
      unawaited(events.close());
    });

    testWidgets('redacted live detail cannot render a legacy structured recap', (tester) async {
      final row = ServerConversation.fromJson({
        ..._conversation(state: ConversationTileState.live, speech: enoughSpeech).toJson(),
        'structured': {'title': 'Legacy', 'overview': 'The legacy paid body.'},
        'summary_covers_through': DateTime(2026, 11, 16, 9).toIso8601String(),
      });
      expect(row.v3?.summaryCoversThrough, isNotNull);
      expect(row.v3?.liveSummary, isNull);
      await tester.pumpWidget(liveSnapshot(LiveSummarySection(
        conversation: row,
        liveInterval: _testRecapInterval,
        stream: (_) => throw StateError('Redacted preview reads must be passive'),
        refresh: () async => false,
        onActiveChanged: (_) {},
      )));
      await tester.pump();
      expect(find.textContaining('The legacy paid body.'), findsNothing);
      expect(find.byKey(const Key('live_summary_coverage')), findsNothing);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a policy refusal removes a saved recap and disables retry or another timer', (tester) async {
      final through = DateTime(2026, 11, 16, 9);
      final conversation = ServerConversation.fromJson({
        ..._conversation(state: ConversationTileState.live, speech: enoughSpeech).toJson(),
        'live_summary': {
          'structured': {'title': 'Launch', 'overview': 'The saved body.'},
          'summary_covers_through': through.toIso8601String(),
        },
      });
      var opens = 0;
      Future<void> show(int tick) => tester.pumpWidget(liveSnapshot(LiveSummarySection(
            conversation: conversation,
            liveInterval: _testRecapInterval,
            open: 1,
            refreshTick: tick,
            stream: (_) {
              opens++;
              return Stream.value(const SummaryFailed('live_recap_unavailable'));
            },
            refresh: () async => false,
            onActiveChanged: (_) {},
          )));
      await show(0);
      await tester.pump();
      expect(find.textContaining('The saved body.'), findsOneWidget);
      expect(opens, 0, reason: 'a saved recap suppresses first-open spend');
      await show(1);
      await tester.pump();
      await tester.pump();
      expect(opens, 1);
      expect(find.textContaining('The saved body.'), findsNothing);
      expect(find.byKey(const Key('live_summary_coverage')), findsNothing);
      expect(find.byKey(const Key('live_summary_recent_transcript')), findsOneWidget);
      expect(find.byKey(const Key('live_summary_catch_up')), findsNothing);
      await show(2);
      await tester.pump();
      expect(opens, 1);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('authoritative correction at the same clock removes the interim preview', (tester) async {
      final events = StreamController<SummaryStreamEvent>();
      final through = DateTime(2026, 11, 16, 9, 20);
      var conversation = _conversation(state: ConversationTileState.live, latestSpeech: through, speech: enoughSpeech);
      late StateSetter rebuild;
      await tester.pumpWidget(_wrap(StatefulBuilder(builder: (context, setState) {
        rebuild = setState;
        return CustomScrollView(slivers: [
          LiveSummarySection(
            liveInterval: _testRecapInterval,
            conversation: conversation,
            open: 1,
            stream: (_) => events.stream,
            refresh: () async => false,
            onActiveChanged: (_) {},
          ),
        ]);
      })));
      await tester.pump();
      rebuild(() {
        conversation = _conversation(
          state: ConversationTileState.live,
          latestSpeech: through.add(const Duration(seconds: 3)),
          speech: enoughSpeech,
        );
        conversation.transcriptSegments.add(TranscriptSegment(
            id: 'later',
            text: 'New speech.',
            speaker: 'SPEAKER_00',
            personId: null,
            isUser: true,
            start: 1200,
            end: 1203,
            translations: []));
      });
      await tester.pump();
      events.add(SummaryDone(Structured('Launch', 'Interim live private body.'), through));
      await tester.pump();
      expect(find.textContaining('Interim live private body.'), findsOneWidget);
      rebuild(() {
        conversation = _conversation(
          state: ConversationTileState.live,
          latestSpeech: through,
          speech: '$enoughSpeech corrected',
        );
      });
      await tester.pump();
      expect(find.textContaining('Interim live private body.'), findsNothing);
      expect(find.byKey(const Key('live_summary_coverage')), findsNothing);
      expect(find.byKey(const Key('live_summary_catch_up')), findsNothing);
      expect(find.byKey(const Key('live_summary_recent_transcript')), findsOneWidget);
      rebuild(() {
        conversation = ServerConversation.fromJson({
          ...conversation.toJson(),
          'home_hidden': true,
        });
      });
      await tester.pump();
      expect(find.byKey(const Key('live_summary_catch_up')), findsNothing);
      expect(find.byKey(const Key('live_summary_recent_transcript')), findsNothing);
      await tester.pumpWidget(const SizedBox());
      unawaited(events.close());
    });

    testWidgets('an account change drops an outstanding live result', (tester) async {
      final events = StreamController<SummaryStreamEvent>();
      final through = DateTime(2026, 11, 16, 9, 20);
      var opens = 0;
      await tester.pumpWidget(_sliver(LiveSummarySection(
        liveInterval: _testRecapInterval,
        conversation: _conversation(state: ConversationTileState.live, latestSpeech: through, speech: enoughSpeech),
        open: 1,
        stream: (_) {
          opens++;
          return events.stream;
        },
        refresh: () async => throw StateError('Do not refresh the old account'),
        onActiveChanged: (_) {},
      )));
      await tester.pump();
      await tester.pump();
      expect(opens, 1);
      await SharedPreferencesUtil().saveString('uid', 'replacement-user');
      events.add(SummaryDone(Structured('Launch', 'Old account private speech.'), through));
      await tester.pump();
      expect(find.textContaining('Old account private speech.'), findsNothing);
      expect(find.byKey(const Key('live_summary_catch_up')), findsNothing);
      expect(events.hasListener, isFalse);
      unawaited(events.close());
    });

    testWidgets('short live speech shows recent transcript instead of inviting model work', (tester) async {
      tester.view.physicalSize = const Size(390, 500);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(liveSnapshot(LiveSummarySection(
        liveInterval: _testRecapInterval,
        conversation: _conversation(
          state: ConversationTileState.live,
          speech: 'Sam will send the updated launch checklist after lunch.',
        ),
        stream: (_) => throw StateError('A short transcript cannot start a stream'),
        refresh: () async => false,
        onActiveChanged: (_) {},
      )));
      await tester.pump();
      expect(find.text('Recent transcript'), findsOneWidget);
      expect(find.text('Sam will send the updated launch checklist after lunch.'), findsOneWidget);
      expect(find.byKey(const Key('live_summary_catch_up')), findsNothing);
      expect(find.byKey(const Key('live_summary_coverage')), findsNothing);
      await shoot(tester, '03-live-summary-short-transcript');
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('still going, then transcribing: no summary write until it is being written', (tester) async {
      var opens = 0;
      var refreshes = 0;
      var conversation = _conversation(state: ConversationTileState.live);
      late StateSetter rebuild;
      final events = StreamController<SummaryStreamEvent>();
      await tester.pumpWidget(_wrap(StatefulBuilder(builder: (context, setState) {
        rebuild = setState;
        return CustomScrollView(slivers: [
          LiveSummarySection(
            liveInterval: _testRecapInterval,
            conversation: conversation,
            stream: (_) {
              opens++;
              return events.stream;
            },
            refresh: () async {
              refreshes++;
              return true;
            },
            onActiveChanged: (_) {},
          ),
        ]);
      })));
      await tester.pump();
      expect(find.text('Summary when this conversation ends'), findsOneWidget);
      expect(find.text('Writing your summary…'), findsNothing);
      expect(find.text('Something went wrong'), findsNothing);
      expect(opens, 0, reason: 'a conversation still going has no summary to write');

      expect(find.byKey(const Key('live_summary_open_transcript')), findsNothing);

      // The page keeps the conversation current (LiveConversationRefresher); the section reads nothing.
      await tester.pump(const Duration(seconds: 30));
      expect(refreshes, 0);

      // It ended, but its transcript is still arriving: still no summary write.
      rebuild(() => conversation = _conversation(state: ConversationTileState.transcribing));
      await tester.pump();
      expect(find.text('Transcribing…'), findsOneWidget);
      expect(find.text('Summary when this conversation ends'), findsNothing);
      expect(opens, 0, reason: 'the summary waits for the whole transcript');

      // Its summary is being written now.
      rebuild(() => conversation = _conversation(state: ConversationTileState.writing));
      await tester.pump();
      expect(opens, 1);
      expect(find.text('Writing your summary…'), findsOneWidget);
      unawaited(events.close());
    });

    testWidgets('pen and skeleton, then the summary streams in, then the stored summary takes over', (tester) async {
      final events = StreamController<SummaryStreamEvent>();
      var refreshes = 0;
      final active = <bool>[];
      await tester.pumpWidget(_sliver(LiveSummarySection(
        liveInterval: _testRecapInterval,
        conversation: _conversation(state: ConversationTileState.writing),
        stream: (_) => events.stream,
        refresh: () async {
          refreshes++;
          return true;
        },
        onActiveChanged: active.add,
      )));
      await tester.pump();
      expect(find.text('Writing your summary…'), findsOneWidget);
      expect(find.byKey(const Key('live_summary_skeleton')), findsOneWidget);
      expect(active, [true]);

      events.add(const SummarySection('## The launch\n- Ship on Thursday'));
      await tester.pump();
      expect(find.byKey(const Key('live_summary_skeleton')), findsNothing);
      expect(find.textContaining('Ship on Thursday'), findsOneWidget);
      expect(find.text('Writing your summary…'), findsOneWidget, reason: 'the pen stays until it is stored');

      events.add(SummaryDone(Structured('Planning', 'We planned.'), DateTime.utc(2026, 11, 16, 9, 30)));
      await tester.pump();
      await tester.pump();
      expect(refreshes, 1);
      expect(find.text('Writing your summary…'), findsNothing);
      expect(active, [true, false]);
      unawaited(events.close());
    });

    testWidgets('another writer: the page re-reads the conversation until the summary lands', (tester) async {
      var conversation = _conversation(state: ConversationTileState.writing);
      var refreshes = 0;
      late StateSetter rebuild;
      await tester.pumpWidget(_wrap(StatefulBuilder(builder: (context, setState) {
        rebuild = setState;
        return CustomScrollView(slivers: [
          LiveSummarySection(
            liveInterval: _testRecapInterval,
            conversation: conversation,
            stream: (_) => Stream.value(const SummaryInProgress()),
            refresh: () async {
              refreshes++;
              return true;
            },
            onActiveChanged: (_) {},
          ),
        ]);
      })));
      await tester.pump();
      await tester.pump(const Duration(seconds: 2));
      await tester.pump(const Duration(seconds: 2));
      expect(refreshes, 2);
      expect(find.text('Writing your summary…'), findsOneWidget);

      rebuild(
          () => conversation = _conversation(state: ConversationTileState.done, covers: DateTime.utc(2026, 11, 16)));
      await tester.pump();
      expect(find.text('Writing your summary…'), findsNothing);
      await tester.pump(const Duration(seconds: 4));
      expect(refreshes, 2, reason: 'polling stopped');
    });

    testWidgets('polling gives up after its window', (tester) async {
      var refreshes = 0;
      await tester.pumpWidget(_sliver(LiveSummarySection(
        liveInterval: _testRecapInterval,
        conversation: _conversation(state: ConversationTileState.writing),
        stream: (_) => Stream.value(const SummaryInProgress()),
        refresh: () async {
          refreshes++;
          return true;
        },
        onActiveChanged: (_) {},
        pollFor: const Duration(seconds: 5),
      )));
      await tester.pump();
      for (var i = 0; i < 6; i++) {
        await tester.pump(const Duration(seconds: 2));
      }
      expect(refreshes, 2, reason: 'a 5 s window at 2 s holds two reads');
      expect(find.text('Writing your summary…'), findsNothing);
      expect(find.byKey(const Key('live_summary_failed')), findsOneWidget,
          reason: 'nothing landed and nothing is stored: offer to try again');
    });

    testWidgets('a summary that arrives whole stays up when the follow-up read fails', (tester) async {
      await tester.pumpWidget(_sliver(LiveSummarySection(
        liveInterval: _testRecapInterval,
        conversation: _conversation(state: ConversationTileState.writing),
        stream: (_) => Stream.value(SummaryDone(Structured('Planning', 'You set the launch for Thursday.'), null)),
        refresh: () async => false,
        onActiveChanged: (_) {},
      )));
      await tester.pump();
      await tester.pump();
      expect(find.textContaining('launch for Thursday'), findsOneWidget);
      expect(find.text('Writing your summary…'), findsNothing);
    });

    testWidgets('a failure with no stored summary offers to try again', (tester) async {
      var opens = 0;
      await tester.pumpWidget(_sliver(LiveSummarySection(
        liveInterval: _testRecapInterval,
        conversation: _conversation(state: ConversationTileState.writing),
        stream: (_) {
          opens++;
          return opens == 1
              ? Stream.value(const SummaryFailed('server'))
              : Stream.value(const SummarySection('- Back on track'));
        },
        refresh: () async => true,
        onActiveChanged: (_) {},
      )));
      await tester.pump();
      await tester.pump();
      expect(find.byKey(const Key('live_summary_failed')), findsOneWidget);
      await tester.tap(find.text('Try Again'));
      await tester.pump();
      await tester.pump();
      expect(opens, 2);
      expect(find.textContaining('Back on track'), findsOneWidget);
    });

    testWidgets('a failure with an older summary stored steps aside', (tester) async {
      final active = <bool>[];
      await tester.pumpWidget(_sliver(LiveSummarySection(
        liveInterval: _testRecapInterval,
        conversation: _conversation(state: ConversationTileState.writing, covers: DateTime.utc(2026, 11, 16, 9)),
        stream: (_) => Stream.value(const SummaryFailed('server')),
        refresh: () async => true,
        onActiveChanged: active.add,
      )));
      await tester.pump();
      await tester.pump();
      expect(find.byKey(const Key('live_summary_failed')), findsNothing);
      expect(find.text('Writing your summary…'), findsNothing);
      expect(active, [true, false]);
    });
  });

  testWidgets('LiveConversationRefresher: one read at a time, in front, until the summary is being written',
      (tester) async {
    var state = ConversationTileState.live;
    var inFront = true;
    var reads = 0;
    Completer<bool>? pending;
    final refresher = LiveConversationRefresher(
      read: () => _conversation(state: state),
      inFront: () => inFront,
      refresh: () {
        reads++;
        pending = Completer<bool>();
        return pending!.future;
      },
    )..start();
    await tester.pump(const Duration(seconds: 15));
    expect(reads, 1);
    await tester.pump(const Duration(seconds: 15));
    expect(reads, 1, reason: 'the first read is still in flight');
    pending!.complete(true);
    await tester.pump(const Duration(seconds: 15));
    expect(reads, 2);
    pending!.complete(true);

    inFront = false;
    await tester.pump(const Duration(seconds: 15));
    expect(reads, 2, reason: 'another route covers the page');
    inFront = true;

    state = ConversationTileState.transcribing;
    await tester.pump(const Duration(seconds: 15));
    expect(reads, 3, reason: 'ended, transcript still arriving');
    pending!.complete(true);

    state = ConversationTileState.writing;
    await tester.pump(const Duration(seconds: 15));
    expect(reads, 3, reason: 'the summary is being written; the section takes it from here');
    refresher.dispose();
  });
}
