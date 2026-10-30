import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/episodes/episode_page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/device_provider.dart';

import '../fakes.dart';
import '../harness.dart';
import 'capture.dart';

class _EpisodeCapture extends AuditCaptureProvider {
  _EpisodeCapture() : super(AuditLive.pendant);

  @override
  String? get topConversationId => 'episode-live-fixture';

  @override
  List<TranscriptSegment> get segments => [
        for (var i = 0; i < 4; i++)
          TranscriptSegment(
            id: 'line-$i',
            text: const [
              'Let us test the live page.',
              'The timer should move every second.',
              'This voice is me.',
              'The newest line keeps my label.'
            ][i],
            speaker: 'SPEAKER_0',
            isUser: true,
            personId: null,
            start: i * 10.0,
            end: i * 10.0 + 8,
            translations: [],
            speakerLabelSource: 'manual',
          ),
      ];
}

final episodeScenarios = <AuditScenario>[
  AuditScenario(
    id: 'episodes-home-processing',
    title: 'Home closing episode: one processing row, then the completed episode',
    page: 'lib/pages/home/home_content.dart (HomeContentPage with HomeFrame chrome)',
    state: 'Fictional dinner episode with two processing members, followed by completion',
    run: (a) async {
      final now = DateTime.now();
      final closed = _closedFixture(day: DateTime(now.year, now.month, now.day));
      final pending = [
        for (final member in closed.members)
          ServerConversation(
            id: member.id,
            createdAt: member.createdAt,
            startedAt: member.startedAt,
            status: ConversationStatus.processing,
            structured: Structured('', ''),
          )
      ];
      final history = ConversationProvider(isSignedIn: () => false)
        ..isLoadingConversations = false
        ..processingConversations = pending;
      final episodes = EpisodeProvider(
        fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
        fetchPage: (from, to, {cursor}) async => ApiSuccess(EpisodePageRead(enabled: true, episodes: [closed])),
      )
        ..debugSetLive(null)
        ..debugSetHomeEpisodes([closed]);
      addTearDown(history.dispose);
      addTearDown(episodes.dispose);
      await a.pump(const HomeFrame(), scaffold: false, providers: [
        ChangeNotifierProvider<ConversationProvider>.value(value: history),
        ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
      ]);
      expect(find.byKey(const Key('home_processing_row')), findsOneWidget);
      expect(find.text('Dinner and plans for the weekend'), findsNothing);
      await a.shot('Episode ended; both members processing in one row', step: 'processing');
      history
        ..processingConversations = []
        ..conversations = closed.members
        ..groupConversationsByDate();
      await a.tester.pump();
      expect(find.byKey(const Key('home_processing_row')), findsNothing);
      expect(find.text('Dinner and plans for the weekend'), findsOneWidget);
      await a.shot('Processing finished; same slot becomes the episode row', step: 'complete');
    },
  ),
  AuditScenario(
    id: 'episodes-home-chrome',
    title: 'Full Home with a live episode today and closed episodes yesterday',
    page: 'lib/pages/home/home_content.dart (HomeContentPage with HomeFrame chrome)',
    state: 'Production Home header and controls, a fictional live episode, and Yesterday episode/conversation rows',
    run: (a) async {
      final now = DateTime.now();
      final today = DateTime(now.year, now.month, now.day);
      final yesterday = today.subtract(const Duration(days: 1));
      final closed = _closedFixture(day: yesterday);
      final unrelated = ServerConversation(
          id: 'garden',
          createdAt: yesterday.add(const Duration(hours: 15, minutes: 20)),
          startedAt: yesterday.add(const Duration(hours: 15, minutes: 20)),
          finishedAt: yesterday.add(const Duration(hours: 15, minutes: 38)),
          structured: Structured('A quick call about the garden', '', emoji: '🌱'));
      final live = Episode(
          id: 'live-today',
          live: true,
          startedAt: now.subtract(const Duration(minutes: 12)),
          lastActivityAt: now,
          title: 'Planning Saturday’s trail',
          conversationIds: const ['episode-live-fixture']);
      final items = [...closed.members, unrelated];
      final history =
          ConversationProvider(isSignedIn: () => true, conversationListFetcher: () async => (items: items, ok: true))
            ..conversations = items
            ..groupConversationsByDate();
      final episodes = EpisodeProvider(
        clock: () => now,
        fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: live)),
        fetchPage: (from, to, {cursor}) async => ApiSuccess(EpisodePageRead(enabled: true, episodes: [closed, live])),
      )
        ..debugSetLive(live)
        ..debugSetHomeEpisodes([closed, live]);
      final capture = _EpisodeCapture();
      final device = AuditDeviceProvider(connected: true, battery: 72, device: auditPendant);
      addTearDown(history.dispose);
      addTearDown(episodes.dispose);
      addTearDown(capture.dispose);
      addTearDown(device.dispose);
      await a.pump(const HomeFrame(), scaffold: false, providers: [
        ChangeNotifierProvider<ConversationProvider>.value(value: history),
        ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
      ]);
      expect(find.text('Today'), findsOneWidget);
      expect(find.text('Yesterday'), findsOneWidget);
      expect(find.text('Planning Saturday’s trail'), findsOneWidget);
      final snippet = a.tester.widget<Text>(
          find.descendant(of: find.byKey(const Key('home_live_episode_preview')), matching: find.byType(Text)));
      expect(snippet.textSpan!.toPlainText(), endsWith('The newest line keeps my label.'));
      expect(find.text('Dinner and plans for the weekend'), findsOneWidget);
      expect(find.text('A quick call about the garden'), findsOneWidget);
      await a.shot('Open full Home with its header, Today live episode and Yesterday rows');
    },
  ),
  AuditScenario(
    id: 'episodes-home-closed',
    title: 'Home with closed episodes in the conversation row style',
    page: 'lib/pages/conversations/conversations_page.dart (ConversationsPage)',
    state: 'Fictional dinner episode with two retained parts, a single-member episode and an unrelated conversation',
    run: (a) async {
      final closed = _closedFixture();
      final morning = ServerConversation(
          id: 'morning',
          createdAt: DateTime(2026, 10, 29, 9, 15),
          startedAt: DateTime(2026, 10, 29, 9, 15),
          finishedAt: DateTime(2026, 10, 29, 9, 42),
          structured: Structured('Coffee and a new book', '', emoji: '☕'));
      final unrelated = ServerConversation(
          id: 'unrelated',
          createdAt: DateTime(2026, 10, 29, 15, 20),
          startedAt: DateTime(2026, 10, 29, 15, 20),
          finishedAt: DateTime(2026, 10, 29, 15, 38),
          structured: Structured('A quick call about the garden', '', emoji: '🌱'));
      final single = Episode(
          id: 'single',
          live: false,
          startedAt: morning.startedAt!,
          lastActivityAt: morning.finishedAt!,
          conversationIds: ['morning'],
          members: [morning]);
      final items = [...closed.members, unrelated, morning];
      final history =
          ConversationProvider(isSignedIn: () => true, conversationListFetcher: () async => (items: items, ok: true))
            ..conversations = items
            ..groupConversationsByDate();
      final episodes = EpisodeProvider(
        fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
        fetchPage: (from, to, {cursor}) async => ApiSuccess(EpisodePageRead(enabled: true, episodes: [closed, single])),
      )
        ..debugSetLive(null)
        ..debugSetHomeEpisodes([closed, single]);
      addTearDown(history.dispose);
      addTearDown(episodes.dispose);
      await a.pump(const ConversationsPage(requestInitialLoad: false), providers: [
        ChangeNotifierProvider<ConversationProvider>.value(value: history),
        ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
      ]);
      expect(find.text('Dinner and plans for the weekend'), findsOneWidget);
      expect(find.textContaining('2 parts'), findsOneWidget);
      expect(find.text('Dinner at the noodle house'), findsNothing);
      expect(find.text('Coffee and a new book'), findsOneWidget);
      await a.shot('Open Home with closed episode rows');
    },
  ),
  AuditScenario(
    id: 'episodes-closed-page',
    title: 'Closed episode summary, tasks and member conversations',
    page: 'lib/pages/episodes/episode_page.dart (EpisodePage)',
    state: 'Fictional 6:56–9:43 PM dinner episode with its summary, a retained task and two conversations',
    run: (a) async {
      await a.pump(EpisodePage(episode: _closedFixture()), scaffold: false);
      expect(find.text('Conversations'), findsOneWidget);
      expect(find.text('Dinner at the noodle house'), findsOneWidget);
      expect(find.text('Pack the picnic for Saturday'), findsOneWidget);
      await a.shot('Open the multi-part dinner episode');
    },
  ),
  AuditScenario(
    id: 'episodes-live-transcript',
    title: 'Live episode transcript and elapsed seconds',
    page: 'lib/pages/episodes/live_episode_page.dart (LiveEpisodePage)',
    state: 'Synthetic live episode at 61 seconds with a manually labeled owner',
    run: (a) async {
      final now = DateTime(2026, 10, 21, 21, 12, 1);
      final episode = Episode(
          id: 'episode-fixture', live: true, startedAt: now.subtract(const Duration(seconds: 61)), lastActivityAt: now);
      final episodes = EpisodeProvider(
        clock: () => now,
        fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: episode)),
      )..debugSetLive(episode);
      final capture = _EpisodeCapture();
      addTearDown(episodes.dispose);
      addTearDown(capture.dispose);
      await a.pump(const LiveEpisodePage(initialTab: LiveEpisodeTab.transcript),
          providers: [
            ChangeNotifierProvider<EpisodeProvider>.value(value: episodes),
            ChangeNotifierProvider<CaptureProvider>.value(value: capture),
          ],
          scaffold: false);
      expect(find.text('Listening now'), findsOneWidget);
      expect(find.text('The newest line keeps my label.'), findsOneWidget);
      await a.shot('Open the live Transcript tab after naming the owner');
    },
  ),
];

Episode _closedFixture({DateTime? day}) {
  final date = day ?? DateTime(2026, 10, 29);
  final start = DateTime(date.year, date.month, date.day, 18, 56);
  final middle = DateTime(date.year, date.month, date.day, 20, 5);
  final end = DateTime(date.year, date.month, date.day, 21, 43);
  return Episode(
    id: 'evening-episode',
    live: false,
    startedAt: start,
    lastActivityAt: end,
    title: 'Dinner and plans for the weekend',
    emoji: '🍜',
    conversationIds: const ['dinner', 'weekend'],
    members: [
      ServerConversation(
          id: 'dinner',
          createdAt: start,
          startedAt: start,
          finishedAt: middle,
          structured: Structured('Dinner at the noodle house', '', emoji: '🍜')),
      ServerConversation(
          id: 'weekend',
          createdAt: middle,
          startedAt: middle,
          finishedAt: end,
          structured: Structured('A weekend in the mountains', '', emoji: '🏕️')),
    ],
    bullets: const [
      'Caught up over dinner and picked a trail for Saturday.',
      'Leave early, bring a picnic, and check the weather on Friday.',
    ],
    items: [
      EpisodeItem(
          id: 'picnic',
          text: 'Pack the picnic for Saturday',
          createdAt: start,
          conversationId: 'weekend',
          status: EpisodeItemStatus.kept)
    ],
  );
}
