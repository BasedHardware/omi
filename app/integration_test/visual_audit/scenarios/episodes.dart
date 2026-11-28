import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/episodes/episode_page.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/episode_provider.dart';

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

Episode _closedFixture({DateTime? day, bool composed = false}) {
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
    moments: [
      if (composed)
        EpisodeMoment(
            id: 'dinner-moment',
            conversationId: 'dinner',
            startedAt: start,
            endedAt: middle,
            points: const [EpisodePoint('Picked a trail for Saturday.')]),
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
