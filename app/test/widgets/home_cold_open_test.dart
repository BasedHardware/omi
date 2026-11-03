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
      }
      ..hiddenNoiseCountsFetcherOverride = (_, __) async => <DateTime, int>{};
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
  testWidgets('Short clips keeps a matched floor member outside the episode overlay', (tester) async {
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
    final retained = ServerConversation(id: 'retained', createdAt: now, structured: Structured('Retained member', ''));
    final conversations = ConversationProvider(
      isSignedIn: () => true,
      conversationListFetcher: () async => (items: [short], ok: true),
    );
    conversations.showShortConversations = true;
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
  for (final delay in [const Duration(milliseconds: 200), const Duration(milliseconds: 800)]) {
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
      )..hiddenNoiseCountsFetcherOverride = (_, __) async => <DateTime, int>{};
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
      expect(find.text('Finishing up…'), findsOneWidget);
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
}
