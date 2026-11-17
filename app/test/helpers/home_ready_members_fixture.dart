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

/// Content-free reproduction of the reported metadata shape: ten READY notes,
/// three settled no-speech outcomes, one separate active recording, and three
/// local pending recordings whose source owner began before Today.
class HomeSettledNoiseFixture {
  HomeSettledNoiseFixture(DateTime now) {
    final day = DateTime(now.year, now.month, now.day);
    members = [
      for (var i = 0; i < 13; i++)
        ServerConversation(
            id: 'settled-shape-$i',
            episodeId: 'settled-shape-owner',
            createdAt: day.add(Duration(hours: 9, minutes: i * 5)),
            startedAt: day.add(Duration(hours: 9, minutes: i * 5)),
            finishedAt: day.add(Duration(hours: 9, minutes: i * 5 + 2)),
            structured: Structured(i < 10 ? 'Ready recording ${i + 1}' : '', i < 10 ? 'Own notes are ready.' : ''),
            homeStep: i < 10 ? 'ready' : 'noise'),
    ];
    waiting = Episode(
        id: 'settled-shape-owner',
        live: false,
        startedAt: day.add(const Duration(hours: 9)),
        lastActivityAt: day.add(const Duration(hours: 11)),
        closedAt: now,
        conversationIds: members.map((m) => m.id).toList(),
        members: members);
    localPending = [
      for (final (i, length) in [
        const Duration(hours: 1, minutes: 45),
        const Duration(minutes: 22),
        const Duration(minutes: 2, seconds: 52)
      ].indexed)
        ServerConversation(
            id: 'older-local-$i',
            episodeId: 'older-local-owner',
            createdAt: day.add(Duration(hours: 1 + i)),
            startedAt: day.add(Duration(hours: 1 + i)),
            finishedAt: day.add(Duration(hours: 1 + i)).add(length),
            status: ConversationStatus.processing,
            structured: Structured('Pending recording', ''),
            homeStep: i == 0 ? null : 'transcribing'),
    ];
    older = Episode(
        id: 'older-local-owner',
        live: false,
        startedAt: day.subtract(const Duration(minutes: 12)),
        lastActivityAt: day.add(const Duration(hours: 4)),
        closedAt: now,
        conversationIds: localPending.map((m) => m.id).toList(),
        members: localPending);
    live = Episode(
        id: 'active-shape-owner',
        live: true,
        startedAt: now.subtract(const Duration(minutes: 20)),
        lastActivityAt: now,
        conversationIds: const ['active-shape-recording']);
  }

  late final List<ServerConversation> members;
  late final List<ServerConversation> localPending;
  late final Episode waiting;
  late final Episode older;
  late final Episode live;
}
