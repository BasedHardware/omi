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
import 'package:omi/providers/home_provider.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:provider/provider.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';
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
  testWidgets('cached older members wait for their full episode range before first paint', (tester) async {
    SharedPreferences.setMockInitialValues({'uid': 'fixture-home'});
    await SharedPreferencesUtil.init();
    final day = DateUtils.dateOnly(DateTime.now().subtract(const Duration(days: 10)));
    final a = ServerConversation(id: 'a', createdAt: day, startedAt: day, structured: Structured('Old fragment A', ''));
    final b = ServerConversation(id: 'b', createdAt: day, startedAt: day, structured: Structured('Old fragment B', ''));
    final page = Completer<({List<ServerConversation> items, bool ok})>();
    var conversationCalls = 0;
    final conversations = ConversationProvider(
      isSignedIn: () => true,
      conversationListFetcher: () {
        conversationCalls++;
        return page.future;
      },
      dailySummariesChecker: () async => false,
    )
      ..conversations = [a, b]
      ..groupedConversations = {
        day: [a, b],
      };
    final overlay = Completer<ApiResult<EpisodePageRead>>();
    DateTime? requestedFrom;
    final episodes = EpisodeProvider(
      fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
      lookup: (_) async => const ApiSuccess(EpisodeRead(enabled: true)),
      fetchPage: (from, to, {cursor}) {
        requestedFrom = from;
        return overlay.future;
      },
    );
    await tester.pumpWidget(
      await buildTypedConversationScreen(
        conversations,
        episodes: episodes,
        initializePreferences: false,
        requestInitialLoad: true,
      ),
    );
    await tester.pump();
    expect(conversationCalls, 1, reason: 'cached rows still join the authoritative first fetch');
    expect(requestedFrom, isNotNull);
    expect(requestedFrom!.isAfter(day), isFalse, reason: 'the initial join must cover cached older pages');
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.text(a.structured.title), findsNothing);
    expect(find.text(b.structured.title), findsNothing);
    overlay.complete(
      ApiSuccess(
        EpisodePageRead(
          enabled: true,
          episodes: [
            Episode(
              id: 'older-episode',
              live: false,
              startedAt: day,
              lastActivityAt: day.add(const Duration(minutes: 20)),
              closedAt: day.add(const Duration(minutes: 20)),
              conversationIds: [a.id, b.id],
              members: [a, b],
              title: 'Older grouped episode',
              moments: [
                EpisodeMoment(
                  id: 'm',
                  conversationId: a.id,
                  startedAt: day,
                  endedAt: day,
                  points: const [EpisodePoint('Fixture')],
                ),
              ],
            ),
          ],
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('Older grouped episode'), findsNothing, reason: 'the list has not landed yet');
    page.complete((items: [a, b], ok: true));
    await tester.pump();
    await tester.pump();
    expect(find.text('Older grouped episode'), findsOneWidget);
    expect(find.text(a.structured.title), findsNothing);
    expect(find.text(b.structured.title), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
    conversations.dispose();
    episodes.dispose();
  });
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
  for (final delay in [
    const Duration(milliseconds: 200),
    const Duration(milliseconds: 800),
    const Duration(seconds: 3)
  ]) {
    testWidgets('cold Home joins staggered providers, overlay delay $delay', (tester) async {
      SharedPreferences.setMockInitialValues({'uid': 'fixture-home'});
      await SharedPreferencesUtil.init();
      final now = DateTime.now();
      final a = ServerConversation(
        id: 'a',
        createdAt: now,
        startedAt: now,
        structured: Structured('Um, so the idea is…', ''),
      );
      final b = ServerConversation(id: 'b', createdAt: now, startedAt: now, structured: Structured('Thank you.', ''));
      final summaries = Completer<bool?>();
      final page = Completer<({List<ServerConversation> items, bool ok})>();
      final overlay = Completer<ApiResult<EpisodePageRead>>();
      var pageCalls = 0;
      final conversations = ConversationProvider(
        conversationListFetcher: () => page.future,
        isSignedIn: () => true,
        dailySummariesChecker: () => summaries.future,
      );
      final episodes = EpisodeProvider(
        fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
        lookup: (_) async => const ApiSuccess(EpisodeRead(enabled: true)),
        fetchPage: (from, to, {cursor}) {
          pageCalls++;
          return overlay.future;
        },
      );
      await tester.pumpWidget(
        await buildTypedConversationScreen(
          conversations,
          episodes: episodes,
          initializePreferences: false,
          requestInitialLoad: true,
        ),
      );
      await tester.pump();
      expect(pageCalls, 1, reason: 'overlay starts concurrently, before conversations land');
      page.complete((items: [a, b], ok: true));
      await tester.pump();
      for (var elapsed = Duration.zero; elapsed < delay; elapsed += const Duration(milliseconds: 50)) {
        await tester.pump(const Duration(milliseconds: 50));
        expect(find.text(a.structured.title), findsNothing);
        expect(find.text(b.structured.title), findsNothing);
        // The skeleton holds through the whole join; no second loader replaces it.
        expect(find.byType(ShimmerWithTimeout), findsWidgets);
        expect(find.text('Finishing up…'), findsNothing);
      }
      overlay.complete(
        ApiSuccess(
          EpisodePageRead(
            enabled: true,
            episodes: [
              Episode(
                id: 'e',
                live: false,
                startedAt: now,
                lastActivityAt: now,
                closedAt: now,
                conversationIds: const ['a', 'b'],
                members: [a, b],
              ),
            ],
          ),
        ),
      );
      await tester.pump();
      await tester.pump();
      expect(find.byType(ShimmerWithTimeout), findsNothing);
      // The joined episode row, still waiting for its summary.
      expect(find.text('Processing…'), findsOneWidget);
      expect(find.text(a.structured.title), findsNothing);
      expect(find.text(b.structured.title), findsNothing);
      final paints = tester.allWidgets.where((w) => w.key == const Key('home_processing_row')).length;
      expect(paints, 1);
      await tester.pump(const Duration(milliseconds: 100));
      expect(pageCalls, 1, reason: 'startup build does not restart the same overlay read');
      summaries.complete(false);
      await tester.pump();
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
  testWidgets('episode-history failure then success never paints or reshuffles member rows', (tester) async {
    SharedPreferences.setMockInitialValues({'uid': 'fixture-home'});
    await SharedPreferencesUtil.init();
    final now = DateTime.now();
    final a = ServerConversation(
        id: 'failure-a', createdAt: now, startedAt: now, structured: Structured('Fragment before retry A', ''));
    final b = ServerConversation(
        id: 'failure-b', createdAt: now, startedAt: now, structured: Structured('Fragment before retry B', ''));
    final conversations = ConversationProvider(
        isSignedIn: () => true,
        conversationListFetcher: () async => (items: [a, b], ok: true),
        dailySummariesChecker: () async => false);
    final retry = Completer<ApiResult<EpisodePageRead>>();
    var reads = 0;
    final episodes = EpisodeProvider(
      fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
      lookup: (_) async => const ApiSuccess(EpisodeRead(enabled: true)),
      fetchPage: (_, __, {cursor}) async {
        reads++;
        if (reads == 1) return const ApiFailure(ApiProblem(ApiProblemKind.transport));
        return retry.future;
      },
    );
    await tester.pumpWidget(await buildTypedConversationScreen(conversations,
        episodes: episodes, initializePreferences: false, requestInitialLoad: true));
    await tester.pump();
    for (var i = 1; i <= 8; i++) {
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.text(a.structured.title), findsNothing, reason: 'a failed read is not ready membership');
      expect(find.text(b.structured.title), findsNothing);
      expect(find.byType(ShimmerWithTimeout), findsWidgets, reason: 'the skeleton holds through the retry');
    }
    expect(reads, 2, reason: 'retry once while keeping first paint joined');
    retry.complete(ApiSuccess(EpisodePageRead(enabled: true, episodes: [
      Episode(
        id: 'recovered-episode',
        live: false,
        startedAt: now,
        lastActivityAt: now,
        closedAt: now,
        title: 'Recovered stable episode',
        conversationIds: [a.id, b.id],
        members: [a, b],
        moments: [
          EpisodeMoment(
              id: 'm', conversationId: a.id, startedAt: now, endedAt: now, points: const [EpisodePoint('Fixture')])
        ],
      )
    ])));
    await tester.pump();
    await tester.pump();
    expect(find.text('Recovered stable episode'), findsOneWidget);
    expect(find.text(a.structured.title), findsNothing);
    expect(find.text(b.structured.title), findsNothing);
    final position = tester.getTopLeft(find.text('Recovered stable episode'));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Recovered stable episode'), findsOneWidget);
    expect(tester.getTopLeft(find.text('Recovered stable episode')), position);
    expect(reads, 2);
    await tester.pumpWidget(const SizedBox.shrink());
    conversations.dispose();
    episodes.dispose();
  });

  for (final boundary in ['pull-to-refresh', 'app resume', 'Home re-entry']) {
    testWidgets('history retry after the deadline preserves rows until $boundary', (tester) async {
      SharedPreferences.setMockInitialValues({'uid': 'fixture-home'});
      await SharedPreferencesUtil.init();
      final now = DateTime.now();
      final a = ServerConversation(
          id: 'late-a', createdAt: now, startedAt: now, structured: Structured('First fallback row', ''));
      final b = ServerConversation(
          id: 'late-b',
          createdAt: now.subtract(const Duration(minutes: 1)),
          startedAt: now.subtract(const Duration(minutes: 1)),
          structured: Structured('Second fallback row', ''));
      final other = ServerConversation(
          id: 'other',
          createdAt: now.subtract(const Duration(minutes: 2)),
          startedAt: now.subtract(const Duration(minutes: 2)),
          structured: Structured('Unrelated row', ''));
      final conversations = ConversationProvider(
          isSignedIn: () => true,
          conversationListFetcher: () async => (items: [a, b, other], ok: true),
          dailySummariesChecker: () async => false);
      final retry = Completer<ApiResult<EpisodePageRead>>();
      var reads = 0;
      final episodes = EpisodeProvider(
        fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
        lookup: (_) async => const ApiSuccess(EpisodeRead(enabled: true)),
        fetchPage: (_, __, {cursor}) async {
          reads++;
          if (reads == 1) return const ApiFailure(ApiProblem(ApiProblemKind.transport));
          return retry.future;
        },
      );
      await tester.pumpWidget(await buildTypedConversationScreen(conversations,
          episodes: episodes, initializePreferences: false, requestInitialLoad: true));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(reads, 2);
      await tester.pump(const Duration(seconds: 2));
      await tester.pump();
      List<String> rowIds() => tester
          .widgetList<ConversationListItem>(find.byType(ConversationListItem))
          .map((row) => row.conversation.id)
          .toList();
      expect(rowIds(), ['late-a', 'late-b', 'other']);
      final positions = [for (final id in rowIds()) tester.getTopLeft(find.byKey(ValueKey(id)))];
      retry.complete(ApiSuccess(EpisodePageRead(enabled: true, episodes: [
        Episode(
          id: 'late-episode',
          live: false,
          startedAt: b.startedAt!,
          lastActivityAt: now,
          closedAt: now,
          title: 'Late grouped episode',
          conversationIds: [a.id, b.id],
          members: [a, b],
          moments: [
            EpisodeMoment(
                id: 'm', conversationId: a.id, startedAt: now, endedAt: now, points: const [EpisodePoint('Fixture')])
          ],
        )
      ])));
      await tester.pump();
      await tester.pump();
      expect(episodes.homeEpisodes.single.id, 'late-episode', reason: 'the retry really published its late result');
      expect(rowIds(), ['late-a', 'late-b', 'other'], reason: 'late grouping must wait for a natural boundary');
      expect([for (final id in rowIds()) tester.getTopLeft(find.byKey(ValueKey(id)))], positions);
      expect(find.text('Late grouped episode'), findsNothing);
      final updated = ServerConversation(
          id: a.id, createdAt: a.createdAt, startedAt: a.startedAt, structured: Structured('Updated in place', ''));
      conversations.updateConversationInSortedList(updated);
      await tester.pump();
      expect(find.text('Updated in place'), findsOneWidget, reason: 'only the grouping is held, not row content');
      expect(rowIds(), ['late-a', 'late-b', 'other']);
      if (boundary == 'pull-to-refresh') {
        // Use the actual pull-to-refresh callback, including both provider reads.
        final refresh = tester.widget<RefreshIndicator>(find.byType(RefreshIndicator)).onRefresh();
        await tester.pump();
        await refresh;
        await tester.pump();
      } else if (boundary == 'app resume') {
        // A transient inactive state (such as a system prompt) is not backgrounding.
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
        await tester.pump();
        expect(rowIds(), ['late-a', 'late-b', 'other']);
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
        await tester.pump();
      } else {
        final pageState = tester.state(find.byType(ConversationsPage));
        final home = tester.element(find.byType(ConversationsPage)).read<HomeProvider>();
        home.setIndex(HomeProvider.tasksTab);
        await tester.pump();
        expect(rowIds(), ['late-a', 'late-b', 'other'], reason: 'leaving does not clear the pin early');
        home.setIndex(HomeProvider.homeTab);
        await tester.pump();
        expect(tester.state(find.byType(ConversationsPage)), same(pageState), reason: 'Home is kept alive');
      }
      expect(rowIds(), ['episode:late-episode', 'other']);
      expect(find.text('Late grouped episode'), findsOneWidget);
      expect(find.byKey(ValueKey(a.id)), findsNothing);
      expect(find.byKey(ValueKey(b.id)), findsNothing);
      await tester.pumpWidget(const SizedBox.shrink());
      conversations.dispose();
      episodes.dispose();
    });
  }

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

  for (final earlyMillis in [0, 300, 600]) {
    testWidgets('failed history has a bounded hold and cancels timers, early dispose at $earlyMillis ms',
        (tester) async {
      SharedPreferences.setMockInitialValues({'uid': 'fixture-home'});
      await SharedPreferencesUtil.init();
      final now = DateTime.now();
      final row = ServerConversation(
          id: 'fallback',
          createdAt: now,
          startedAt: now,
          structured: Structured('Reachable during persistent outage', 'Fixture overview'));
      final conversations = ConversationProvider(
          isSignedIn: () => true,
          conversationListFetcher: () async => (items: [row], ok: true),
          dailySummariesChecker: () async => false);
      var reads = 0;
      final episodes = EpisodeProvider(
        fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
        lookup: (_) async => const ApiSuccess(EpisodeRead(enabled: true)),
        fetchPage: (_, __, {cursor}) async {
          reads++;
          return const ApiFailure(ApiProblem(ApiProblemKind.transport));
        },
      );
      await tester.pumpWidget(await buildTypedConversationScreen(conversations,
          episodes: episodes, initializePreferences: false, requestInitialLoad: true));
      await tester.pump();
      // Advance each retry separately; a large pump schedules the next delay from its end.
      for (var i = 0; i < (earlyMillis == 300 ? 3 : 6); i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(find.byType(ShimmerWithTimeout), findsWidgets, reason: 'the skeleton is the only loading state');
      expect(find.text('Finishing up…'), findsNothing);
      expect(find.text(row.structured.title), findsNothing);
      expect(reads, earlyMillis == 300 ? 2 : 3, reason: 'startup retries are bounded and leave with Home');
      if (earlyMillis == 0) {
        await tester.pump(const Duration(milliseconds: 1500));
        await tester.pump();
        expect(find.byType(ShimmerWithTimeout), findsNothing);
        expect(find.text(row.structured.title), findsOneWidget, reason: 'persistent failure cannot block Home forever');
      }
      await tester.pumpWidget(const SizedBox.shrink());
      conversations.dispose();
      episodes.dispose();
    });
  }
}
