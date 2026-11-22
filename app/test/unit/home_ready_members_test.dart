import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/home_rows.dart';
import 'package:omi/utils/conversations/home_member_fallback.dart';

final _at = DateTime(2026, 11, 15, 9);

ServerConversation _member(int index, String step, {bool locked = false}) => ServerConversation(
      id: 'member-$index',
      episodeId: 'owner',
      createdAt: _at.add(Duration(minutes: index)),
      startedAt: _at.add(Duration(minutes: index)),
      finishedAt: _at.add(Duration(minutes: index + 1)),
      structured: step == 'noise' ? Structured('', '') : Structured('Notes $index', 'Member overview $index'),
      status: step == 'failed' ? ConversationStatus.failed : ConversationStatus.completed,
      homeStep: step,
      isLocked: locked,
    );

Episode _owner(List<ServerConversation> members, {bool live = false, bool composed = false}) => Episode(
      id: 'owner',
      live: live,
      startedAt: _at,
      lastActivityAt: _at.add(const Duration(minutes: 5)),
      closedAt: live ? null : _at.add(const Duration(minutes: 5)),
      lede: composed && !live ? 'Episode notes' : '',
      moments: composed
          ? [
              EpisodeMoment(
                  id: 'moment',
                  conversationId: members.first.id,
                  startedAt: _at,
                  endedAt: _at,
                  points: const [EpisodePoint('Episode notes')])
            ]
          : const [],
      conversationIds: members.map((m) => m.id).toList(),
      members: members,
    );

List<HomeRow> _rows(List<ServerConversation> members, Episode episode,
        {bool listening = false, bool rollback = false}) =>
    buildHomeRows(members, [episode],
        enabled: true,
        groupAwaitingTranscript: true,
        processingConversations: members.where((m) => m.homeStep == 'transcribing').toList(),
        singleProcessingRow: !rollback,
        now: _at.add(const Duration(minutes: 6)),
        liveEpisodeId: listening ? episode.id : null,
        liveConversationIds: listening ? episode.conversationIds.toSet() : const {});

void main() {
  test('empty terminal outcomes never fall back to awaiting a transcript', () {
    for (final step in ['ready', 'noise', 'failed', 'writing_notes']) {
      final empty = ServerConversation(
          id: 'empty-$step',
          createdAt: _at,
          status: ConversationStatus.completed,
          homeStep: step,
          structured: Structured('', ''));
      expect(awaitingHomeTranscript(empty), isFalse, reason: 'server $step is authoritative');
    }
    final legacy = ServerConversation(
        id: 'legacy-empty', createdAt: _at, status: ConversationStatus.completed, structured: Structured('', ''));
    expect(awaitingHomeTranscript(legacy), isTrue);
  });

  for (final live in [false, true]) {
    for (final composed in [false, true]) {
      for (final listening in live ? [false, true] : [false]) {
        for (final a in ['ready', 'noise', 'transcribing', 'writing_notes', 'failed']) {
          for (final b in ['ready', 'noise', 'transcribing', 'writing_notes', 'failed']) {
            test('members $a/$b live=$live composed=$composed listening=$listening', () {
              final members = [_member(0, a), _member(1, b)];
              final owner = _owner(members, live: live, composed: composed);
              final rows = _rows(members, owner, listening: listening);
              final pending = rows.where((r) => r.isProcessing).toList();
              expect(pending.length, lessThanOrEqualTo(1));
              final memberRows = rows.where((r) => !r.isProcessing && r.conversation.id.startsWith('member-')).toList();
              final readyIds = members.where((m) => m.homeStep == 'ready').map((m) => m.id).toSet();
              if (live || !composed) {
                expect(
                    memberRows.where((r) => r.conversation.homeStep == 'ready').map((r) => r.conversation.id).toSet(),
                    readyIds);
                expect(
                    pending
                        .expand((r) => r.episode!.members)
                        .every((m) => ['transcribing', 'writing_notes'].contains(m.homeStep)),
                    isTrue);
                expect(
                    pending.fold<int>(0, (n, r) => n + r.count),
                    listening
                        ? 0
                        : members.where((m) => ['transcribing', 'writing_notes'].contains(m.homeStep)).length);
                if (pending.isNotEmpty) {
                  expect(pending.single.step,
                      members.any((m) => m.homeStep == 'transcribing') ? HomeStep.transcribing : HomeStep.writingNotes);
                }
              } else {
                expect(rows.where((r) => r.isTemporaryMember), isEmpty);
                expect(pending, isEmpty, reason: 'composed notes never regress to processing');
              }
              final represented = <String>[
                if (listening) ...members.where((m) => m.homeStep != 'ready').map((m) => m.id),
                for (final row in rows)
                  if (row.isProcessing || (row.episode != null && row.conversation.id.startsWith('episode:')))
                    ...row.episode!.members.map((m) => m.id)
                  else
                    row.conversation.id,
              ];
              // Noise may remain a source on the composed page, but never
              // creates work or a separate row on Home.
              final noiseIds = members.where((m) => m.homeStep == 'noise').map((m) => m.id).toSet();
              expect(represented.toSet().difference(noiseIds),
                  members.where((m) => m.homeStep != 'noise').map((m) => m.id).toSet());
              expect(represented.length, represented.toSet().length, reason: 'each member has one Home owner');
              final reversed = _rows(members.reversed.toList(), owner, listening: listening);
              expect(reversed.map((r) => r.conversation.id), rows.map((r) => r.conversation.id));
            });
          }
        }
      }
    }
  }

  test('READY rows use real identities and are replaced atomically in both API arrival orders', () {
    final ready = [_member(0, 'ready'), _member(1, 'ready')];
    final pending = [_member(0, 'transcribing'), _member(1, 'transcribing')];
    final uncomposed = _owner(ready);
    final composed = _owner(ready, composed: true);
    expect(_rows(ready, uncomposed).map((r) => r.conversation.id), ['member-1', 'member-0']);
    for (final sequence in [
      [_rows(pending, _owner(pending)), _rows(ready, uncomposed), _rows(ready, composed)],
      [_rows(pending, _owner(pending)), _rows(pending, composed), _rows(ready, composed)],
    ]) {
      for (final rows in sequence) {
        final ownerRows = rows.where((r) => r.conversation.id == 'episode:owner').toList();
        if (ownerRows.any((r) => !r.isProcessing)) {
          expect(rows.where((r) => r.conversation.id.startsWith('member-')), isEmpty);
        }
        expect(rows.expand((r) => r.episode?.members.map((m) => m.id) ?? [r.conversation.id]).toSet(),
            ready.map((m) => m.id).toSet());
      }
    }
    final rollback = _rows(ready, uncomposed, rollback: true);
    expect(rollback.single.isProcessing, isTrue);
  });

  test('noise is omitted and locked members stay actionable outside pending count', () {
    final ready = _member(0, 'ready'), pending = _member(1, 'transcribing'), noise = _member(2, 'noise');
    final locked = _member(3, 'ready', locked: true);
    final members = [ready, pending, noise, locked];
    final rows = _rows(members, _owner(members));
    expect(rows.where((r) => r.isProcessing).single.count, 1);
    expect(rows.where((r) => r.conversation.id == noise.id), isEmpty);
    expect(rows.singleWhere((r) => r.conversation.id == locked.id).conversation.isLocked, isTrue);
  });

  test('metadata-only READY rows retain their owner through outage layout, deletion and Undo', () {
    final members = [_member(0, 'ready'), _member(1, 'transcribing')];
    final owner = _owner(members);
    final layout = HomeEpisodeLayout([owner]);
    List<HomeRow> project(List<Episode> episodes, {Set<String> deleted = const {}}) => buildHomeRows([], episodes,
        enabled: true,
        groupAwaitingTranscript: true,
        deletedIds: deleted,
        processingConversations: [members.first],
        now: _at.add(const Duration(minutes: 6)));
    final before = project([owner]);
    expect(before.singleWhere((r) => r.isProcessing).count, 1);
    final ready = before.singleWhere((r) => r.conversation.id == members.first.id);
    expect(ready.isTemporaryMember, isTrue);
    expect(ready.episode!.id, owner.id);
    final duringOutage = project(layout.apply([], standaloneIds: const {}));
    expect(duringOutage.map((r) => r.conversation.id), before.map((r) => r.conversation.id));
    expect(project([owner], deleted: {members.first.id}).where((r) => r.isTemporaryMember), isEmpty);
    expect(project([owner]).where((r) => r.isTemporaryMember).single.conversation.id, members.first.id);
    final after = project(layout.apply([_owner(members, composed: true)], standaloneIds: const {}));
    expect(after.single.conversation.id, 'episode:owner');
    expect(after.single.isTemporaryMember, isFalse);
    expect(after.single.episode!.members.map((m) => m.id).toSet(), members.map((m) => m.id).toSet());
  });
}
