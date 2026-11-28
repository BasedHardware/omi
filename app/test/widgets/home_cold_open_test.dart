import 'package:visibility_detector/visibility_detector.dart';
import 'package:omi/env/env.dart';
import '../helpers/home_fixture_env.dart';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import '../support/typed_conversation_screen.dart';

class _ThrowingInitialConversations extends ConversationProvider {
  _ThrowingInitialConversations() : super(isSignedIn: () => true);
  @override
  Future<void> getInitialConversations({bool checkDailySummaries = true}) async => throw StateError('fixture failure');
}

void main() {
  final previousVisibilityInterval = VisibilityDetectorController.instance.updateInterval;
  setUpAll(() {
    Env.init(HomeFixtureEnv());
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
  });
  tearDownAll(() => VisibilityDetectorController.instance.updateInterval = previousVisibilityInterval);
  for (final speakerSearch in [false, true]) {
    testWidgets('Filtered Home keeps exact source match, speaker search=$speakerSearch', (tester) async {
      SharedPreferences.setMockInitialValues({'uid': 'fixture-home'});
      await SharedPreferencesUtil.init();
      final now = DateTime.now();
      final short = ServerConversation(
        id: 'floor',
        createdAt: now,
        startedAt: now,
        structured: Structured('Short clip match', ''),
        discarded: true,
      );
      final retained =
          ServerConversation(id: 'retained', createdAt: now, structured: Structured('Retained member', ''));
      final conversations = ConversationProvider(
        isSignedIn: () => true,
        conversationListFetcher: () async => (items: [short], ok: true),
      );
      conversations.showShortConversations = !speakerSearch;
      conversations.selectedSpeakerId = speakerSearch ? 'fixture-speaker' : null;
      conversations.searchedConversations = speakerSearch ? [short] : [];
      conversations.conversations = [short];
      conversations.groupedConversations = {
        DateTime(now.year, now.month, now.day): [short],
      };
      final episodes = EpisodeProvider(
        fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
        lookup: (_) async => const ApiSuccess(EpisodeRead(enabled: true)),
        fetchPage: (_, __, {cursor}) async => ApiSuccess(
          EpisodePageRead(
            enabled: true,
            episodes: [
              Episode(
                id: 'e',
                live: false,
                startedAt: now,
                lastActivityAt: now,
                conversationIds: ['floor', 'retained'],
                members: [retained],
              ),
            ],
          ),
        ),
      );
      await episodes.refreshLive();
      await episodes.refreshHome(now.subtract(const Duration(days: 1)), now.add(const Duration(days: 1)));
      await tester.pumpWidget(
        await buildTypedConversationScreen(conversations, episodes: episodes, initializePreferences: false),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 250));
      expect(find.byKey(ValueKey(short.id)), findsOneWidget, reason: 'the exact source row remains reachable');
      expect(find.text('Retained member'), findsNothing);
      await tester.pumpWidget(const SizedBox.shrink());
      conversations.dispose();
      episodes.dispose();
    });
  }
  testWidgets('a thrown conversation fetch releases the initial overlay hold', (tester) async {
    SharedPreferences.setMockInitialValues({'uid': 'fixture-home'});
    await SharedPreferencesUtil.init();
    final now = DateTime.now();
    final row = ServerConversation(
        id: 'cached',
        createdAt: now,
        startedAt: now,
        structured: Structured('Cached reachable conversation', 'Fixture overview'));
    final conversations = _ThrowingInitialConversations()
      ..conversations = [row]
      ..groupedConversations = {
        DateUtils.dateOnly(now): [row]
      };
    final overlay = Completer<ApiResult<EpisodePageRead>>();
    final episodes = EpisodeProvider(
      fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
      lookup: (_) async => const ApiSuccess(EpisodeRead(enabled: true)),
      fetchPage: (_, __, {cursor}) => overlay.future,
    );
    await tester.pumpWidget(await buildTypedConversationScreen(conversations,
        episodes: episodes, initializePreferences: false, requestInitialLoad: true));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    expect(tester.takeException(), isNull);
    expect(find.text('Finishing up…'), findsNothing);
    expect(find.text(row.structured.title), findsOneWidget);
    overlay.complete(const ApiSuccess(EpisodePageRead(enabled: true)));
    await tester.pump();
    await tester.pumpWidget(const SizedBox.shrink());
    conversations.dispose();
    episodes.dispose();
  });

  testWidgets('selected day keeps its 00:30 member when the episode began at 23:00 yesterday', (tester) async {
    SharedPreferences.setMockInitialValues({'uid': 'fixture-home'});
    await SharedPreferencesUtil.init();
    final day = DateUtils.dateOnly(DateTime.now().subtract(const Duration(days: 2)));
    final previous = day.subtract(const Duration(hours: 1));
    final afterMidnight = day.add(const Duration(minutes: 30));
    final a = ServerConversation(
        id: 'previous-day',
        createdAt: previous,
        startedAt: previous,
        finishedAt: previous.add(const Duration(minutes: 10)),
        structured: Structured('Previous-day member', ''));
    final b = ServerConversation(
        id: 'selected-day',
        createdAt: afterMidnight,
        startedAt: afterMidnight,
        finishedAt: afterMidnight.add(const Duration(minutes: 10)),
        structured: Structured('00:30 selected member', ''));
    final conversations = ConversationProvider(isSignedIn: () => true)
      ..conversations = [a, b]
      ..selectedStartDate = day
      ..selectedEndDate = day
      ..groupedConversations = {
        day: [b]
      };
    final episodes = EpisodeProvider(
      fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
      lookup: (_) async => const ApiSuccess(EpisodeRead(enabled: true)),
      fetchPage: (_, __, {cursor}) async => ApiSuccess(EpisodePageRead(enabled: true, episodes: [
        Episode(
          id: 'cross-midnight',
          live: false,
          startedAt: previous,
          lastActivityAt: afterMidnight,
          closedAt: afterMidnight,
          title: 'Previous-day episode',
          conversationIds: [a.id, b.id],
          members: [a, b],
          moments: [
            EpisodeMoment(
                id: 'm',
                conversationId: a.id,
                startedAt: previous,
                endedAt: afterMidnight,
                points: const [EpisodePoint('Fixture')])
          ],
        )
      ])),
    );
    await episodes.refreshLive();
    await episodes.refreshHome(previous, day.add(const Duration(days: 1)));
    await tester.pumpWidget(
        await buildTypedConversationScreen(conversations, episodes: episodes, initializePreferences: false));
    await tester.pump();
    expect(find.byKey(ValueKey(b.id)), findsOneWidget);
    expect(find.text(b.structured.title), findsOneWidget);
    expect(find.text(a.structured.title), findsNothing);
    expect(find.text('Previous-day episode'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
    conversations.dispose();
    episodes.dispose();
  });
}
