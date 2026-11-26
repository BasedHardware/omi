import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';

/// Fictional shape of the owner's report, with no account data or identifiers.
class HomeOneProcessingFixture {
  HomeOneProcessingFixture(DateTime now, {bool serverOnly = false}) {
    final day = DateTime(now.year, now.month, now.day);
    ServerConversation recording(String id, DateTime at, int seconds, String step) => ServerConversation(
          id: id,
          createdAt: at,
          startedAt: at,
          finishedAt: at.add(Duration(seconds: seconds)),
          structured:
              Structured(step == 'ready' ? 'Finished episode fixture' : (serverOnly ? 'Pending fixture' : ''), ''),
          status: step != 'ready' && (serverOnly || step == 'writing_notes')
              ? ConversationStatus.processing
              : ConversationStatus.completed,
          homeStep: step,
        );
    Episode episode(String id, List<ServerConversation> members) => Episode(
          id: id,
          live: false,
          startedAt: members.first.startedAt!,
          lastActivityAt: members.last.finishedAt!,
          closedAt: serverOnly ? now.subtract(const Duration(hours: 1)) : now,
          title: serverOnly ? 'Pending fixture' : '',
          members: members,
          conversationIds: members.map((m) => m.id).toList(),
        );
    final early = [
      for (var i = 0; i < 9; i++) recording('early-$i', day.add(Duration(hours: 9, minutes: i)), 30, 'transcribing'),
    ];
    final later = [
      for (var i = 0; i < 15; i++) recording('later-$i', day.add(Duration(hours: 13, minutes: i)), 30, 'transcribing'),
    ];
    final closing = [
      for (final (i, seconds) in [101, 577, 11].indexed)
        recording('closing-$i', day.add(Duration(hours: 14, minutes: i * 10)), seconds, 'writing_notes'),
    ];
    pending = [...closing, ...later, ...early];
    finished = recording('finished', day.add(const Duration(hours: 11, minutes: 3)), 99 * 60, 'ready');
    episodes = [
      episode('early', early),
      episode('later', later),
      for (var i = 0; i < closing.length; i++) episode('closing-$i', [closing[i]]),
    ];
    live = Episode(
      id: 'live-fixture',
      live: true,
      startedAt: now.subtract(const Duration(hours: 5, minutes: 5)),
      lastActivityAt: now,
      conversationIds: const ['live-capture'],
    );
  }

  late final List<ServerConversation> pending;
  late final ServerConversation finished;
  late final List<Episode> episodes;
  late final Episode live;
}
