import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/home_rows.dart';
import 'package:omi/services/capture/optimistic_processing.dart';

final _day = DateTime(2026, 11, 15, 9);

ServerConversation _recording(String id, int minute, {String step = 'writing_notes', String? episodeId}) =>
    ServerConversation(
      id: id,
      createdAt: _day.add(Duration(minutes: minute)),
      startedAt: _day.add(Duration(minutes: minute)),
      finishedAt: _day.add(Duration(minutes: minute + 1)),
      structured: Structured('Fixture $id', ''),
      homeStep: step,
      episodeId: episodeId,
    );

void main() {
  test('episode step uses current server membership before a stale local processing label', () {
    final metadata = _recording('member', 1, step: 'transcribing');
    final local = _recording('member', 1, step: 'writing_notes');
    final episode = Episode(
        id: 'owner',
        live: false,
        startedAt: _day,
        lastActivityAt: _day,
        members: [metadata],
        conversationIds: [metadata.id]);
    final rows =
        buildHomeRows([], [episode], enabled: true, groupAwaitingTranscript: true, processingConversations: [local]);
    expect(rows.single.step, HomeStep.transcribing);
  });
  test('optimistic aliases count once and keep the real member reachable', () {
    final member = _recording('target', 1);
    final placeholder = OptimisticProcessingPlaceholder.conversation(targetConversationId: member.id);
    final episode = Episode(
        id: 'owner',
        live: false,
        startedAt: _day,
        lastActivityAt: _day,
        members: [member],
        conversationIds: [member.id]);
    final rows = buildHomeRows([placeholder, member], [episode],
        enabled: true, groupAwaitingTranscript: true, processingConversations: [placeholder, member]);
    expect(rows.single.count, 1);
    expect(rows.single.episode!.members.single.id, member.id);
    expect(rows.single.episodeConversationIds, {member.id});
    final unseen = buildHomeRows([placeholder], [], enabled: false, groupAwaitingTranscript: true);
    expect(unseen.single.episode!.members.single.id, member.id,
        reason: 'the placeholder page must use its real target, even before the first list read');
  });
  test('Home capability off keeps one aggregate across finished rows', () {
    final rows = buildHomeRows([
      _recording('new', 30),
      _recording('ready', 20, step: 'ready'),
      _recording('old', 10),
    ], [], enabled: false, groupAwaitingTranscript: true, processingTodayOnly: false);
    expect(rows.map((row) => row.isProcessing), [true, false]);
    expect(rows.first.count, 2);
  });
  for (final n in [0, 1, 3]) {
    for (final m in [0, 1, 4]) {
      test('$n pending episodes + $m pending recordings across finished rows have one owner', () {
        final episodes = [
          for (var i = 0; i < n; i++)
            Episode(
              id: 'episode-$i',
              live: false,
              startedAt: _day.add(Duration(minutes: i * 10)),
              lastActivityAt: _day.add(Duration(minutes: i * 10 + 2)),
              conversationIds: ['member-$i'],
              members: [_recording('member-$i', i * 10)],
            ),
        ];
        final standalone = [for (var i = 0; i < m; i++) _recording('standalone-$i', i * 10 + 5, step: 'transcribing')];
        final finished = [for (var i = 0; i < 5; i++) _recording('finished-$i', i * 10 + 3, step: 'ready')];
        final failure = _recording('failure', 17, step: 'failed');
        final pending = [...episodes.expand((e) => e.members), ...standalone];
        final rows = buildHomeRows([...pending, ...finished, failure], episodes,
            enabled: true,
            groupAwaitingTranscript: true,
            processingConversations: pending,
            processingTitle: 'Processing',
            now: _day.add(const Duration(hours: 1)));
        final processing = rows.where((r) => r.isProcessing).toList();
        expect(processing.length, n + m == 0 ? 0 : 1);
        expect(rows.where((r) => !r.isProcessing).map((r) => r.conversation.id).toSet(),
            {...finished.map((c) => c.id), failure.id});
        if (processing.isEmpty) return;
        final row = processing.single;
        expect(rows.first, same(row), reason: 'even a newer finished row cannot precede processing');
        expect(row.count, n + m);
        expect(row.step, m > 0 ? HomeStep.transcribing : HomeStep.writingNotes);
        expect(row.episode!.members.map((c) => c.id).toSet(), pending.map((c) => c.id).toSet());
        expect(row.episodeConversationIds, pending.map((c) => c.id).toSet());
        final owners = row.processingEpisodes.isEmpty ? [row.episode!] : row.processingEpisodes;
        expect(owners.where((e) => e.id.isNotEmpty).map((e) => e.id).toSet(), episodes.map((e) => e.id).toSet());
      });
    }
  }

  test('overlapping episode metadata and local entries count each recording once', () {
    final a = _recording('a', 1), b = _recording('b', 2), c = _recording('c', 3, step: 'transcribing');
    final episode = Episode(
      id: 'real',
      live: false,
      startedAt: _day,
      lastActivityAt: _day,
      conversationIds: ['a', 'b'],
      members: [a, b],
    );
    final rows = foldProcessingRuns([
      HomeRow(a, episode: episode, episodeConversationIds: {'a', 'b'}, isProcessing: true, step: HomeStep.writingNotes),
      HomeRow(b),
      HomeRow(c),
    ], processingTitle: 'Processing');
    expect(rows.single.count, 3);
    expect(rows.single.episodeConversationIds, {'a', 'b', 'c'});
    expect(rows.single.processingEpisodes.single.id, 'real');
    expect(rows.single.step, HomeStep.transcribing);
  });

  test('a failed recording keeps its terminal row even with an explicit episode owner', () {
    final failed = _recording('failed-member', 1, step: 'failed', episodeId: 'owner');
    final pending = _recording('pending-member', 2);
    final episode = Episode(
        id: 'owner',
        live: false,
        startedAt: _day,
        lastActivityAt: _day,
        members: [failed, pending],
        conversationIds: [failed.id, pending.id]);
    final rows = buildHomeRows([failed, pending], [episode],
        enabled: true, groupAwaitingTranscript: true, processingConversations: [failed, pending]);
    expect(rows.where((r) => r.isProcessing).single.count, 1);
    final terminal = rows.singleWhere((r) => r.conversation.id == failed.id);
    expect(terminal.isProcessing, isFalse);
    expect(terminal.episode, isNull);
  });
}
