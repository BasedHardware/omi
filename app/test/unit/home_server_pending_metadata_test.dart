import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/home_rows.dart';

final _at = DateTime(2026, 11, 15, 9);

ServerConversation _member(String id, int minute, String step) => ServerConversation(
      id: id,
      createdAt: _at.add(Duration(minutes: minute)),
      startedAt: _at.add(Duration(minutes: minute)),
      finishedAt: _at.add(Duration(minutes: minute + 1)),
      status: ConversationStatus.processing,
      structured: Structured('Fixture', ''),
      homeStep: step,
    );

void main() {
  for (final step in ['transcribing', 'writing_notes']) {
    for (final shape in [(1, 0), (3, 2)]) {
      test('server-only $step metadata survives summary timeout with ${shape.$1} episodes and ${shape.$2} recordings',
          () {
        final episodes = [
          for (var i = 0; i < shape.$1; i++)
            Episode(
              id: 'owner-$i',
              live: false,
              title: 'Pending fixture $i',
              startedAt: _at.add(Duration(minutes: i * 10)),
              lastActivityAt: _at.add(Duration(minutes: i * 10 + 2)),
              closedAt: _at.add(Duration(minutes: i * 10 + 3)),
              members: [for (var j = 0; j < 2; j++) _member('member-$i-$j', i * 10 + j, step)],
              conversationIds: [for (var j = 0; j < 2; j++) 'member-$i-$j'],
            ),
        ];
        final standalone = [for (var i = 0; i < shape.$2; i++) _member('standalone-$i', i * 10 + 5, step)];
        final finished = ServerConversation(
            id: 'finished',
            createdAt: _at.add(const Duration(minutes: 15)),
            structured: Structured('Finished fixture', ''),
            homeStep: 'ready');
        final rows = buildHomeRows([...standalone, finished], episodes,
            enabled: true, groupAwaitingTranscript: true, now: _at.add(const Duration(hours: 4)));
        final pending = rows.where((r) => r.isProcessing).single;
        expect(rows.first, same(pending));
        expect(pending.count, shape.$1 * 2 + shape.$2);
        expect(pending.step, step == 'transcribing' ? HomeStep.transcribing : HomeStep.writingNotes);
        expect(pending.episode!.members.map((m) => m.id).toSet(), {
          for (final episode in episodes) ...episode.conversationIds,
          for (final recording in standalone) recording.id,
        });
        final owners = pending.processingEpisodes.isEmpty ? [pending.episode!] : pending.processingEpisodes;
        expect(owners.map((e) => e.id).toSet(), episodes.map((e) => e.id).toSet());
        expect(rows.where((r) => !r.isProcessing).single.conversation.id, finished.id);
      });
    }
  }
}
