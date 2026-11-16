import 'dart:async';

import 'package:flutter/material.dart';
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
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/widgets/live_summary_section.dart';
import 'package:omi/pages/conversations/widgets/conversation_state_tile.dart';
import 'package:omi/pages/conversations/widgets/day_summary_link.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

ServerConversation _conversation({ConversationTileState? state, DateTime? covers}) => ServerConversation(
      id: 'c1',
      createdAt: DateTime(2026, 11, 16, 9),
      startedAt: DateTime(2026, 11, 16, 9),
      structured: Structured('Planning the launch', '', emoji: '🚀', category: 'work'),
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
    SharedPreferences.setMockInitialValues({});
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

  group('LiveSummarySection', () {
    testWidgets('pen and skeleton, then the summary streams in, then the stored summary takes over', (tester) async {
      final events = StreamController<SummaryStreamEvent>();
      var refreshes = 0;
      final active = <bool>[];
      await tester.pumpWidget(_sliver(LiveSummarySection(
        conversation: _conversation(state: ConversationTileState.live),
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
        conversation: _conversation(state: ConversationTileState.live),
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
        conversation: _conversation(state: ConversationTileState.live),
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
        conversation: _conversation(state: ConversationTileState.live, covers: DateTime.utc(2026, 11, 16, 9)),
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
}
