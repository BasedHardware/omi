import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/gen/episodes_wire.g.dart';
import 'package:omi/backend/schema/structured.dart';

/// Fictional notes/owners only. Exercises the actual member wire adapter too.
class HomeReadyMembersFixture {
  HomeReadyMembersFixture(DateTime now) {
    final at = DateTime(now.year, now.month, now.day, 9);
    members = [
      for (var i = 0; i < 4; i++)
        ServerConversation(
          id: 'ready-fixture-$i',
          episodeId: 'ready-fixture-owner',
          createdAt: at.add(Duration(minutes: i * 10)),
          startedAt: at.add(Duration(minutes: i * 10)),
          finishedAt: at.add(Duration(minutes: i * 10 + 8)),
          structured: Structured(i < 2 ? 'Ready recording ${i + 1}' : 'Pending recording',
              i < 2 ? 'Own recording notes ${i + 1}: the checklist is ready.' : '',
              emoji: '💬'),
          homeStep: i < 2 ? 'ready' : (i == 2 ? 'transcribing' : 'writing_notes'),
        ),
    ];
    waiting = Episode.fromGenerated(GeneratedEpisode.fromJson({
      'id': 'ready-fixture-owner',
      'status': 'closed',
      'started_at': at.toUtc().toIso8601String(),
      'last_activity_at': at.add(const Duration(minutes: 38)).toUtc().toIso8601String(),
      'closed_at': now.toUtc().toIso8601String(),
      'conversation_ids': members.map((m) => m.id).toList(),
      'members': [
        for (final m in members)
          {
            'id': m.id,
            'title': m.structured.title,
            'gist': m.structured.overview,
            'status': 'completed',
            'home_step': m.homeStep,
            'started_at': m.startedAt!.toUtc().toIso8601String(),
            'finished_at': m.finishedAt!.toUtc().toIso8601String()
          },
      ],
    }));
    composed = Episode(
      id: waiting.id,
      live: false,
      startedAt: waiting.startedAt,
      lastActivityAt: waiting.lastActivityAt,
      closedAt: now,
      title: 'Combined episode fixture',
      lede: 'The recording notes are now composed together.',
      conversationIds: waiting.conversationIds,
      members: members,
    );
    live = Episode(
        id: 'separate-live-fixture',
        live: true,
        startedAt: now.subtract(const Duration(minutes: 20)),
        lastActivityAt: now,
        conversationIds: const ['current-live-recording']);
  }
  late final List<ServerConversation> members;
  late final Episode waiting;
  late final Episode composed;
  late final Episode live;
}
