import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/home_rows.dart';

final start = DateTime(2026, 10, 29, 22);
ServerConversation conversation(String id, {bool discarded = false, int hours = 0}) => ServerConversation(
      id: id,
      createdAt: start.add(Duration(hours: hours)),
      startedAt: start.add(Duration(hours: hours)),
      finishedAt: start.add(Duration(hours: hours + 1)),
      discarded: discarded,
      structured: Structured('Title $id', '', emoji: '☕'),
    );
final composedMoments = [
  EpisodeMoment(
    id: 'm',
    conversationId: 'a',
    startedAt: start,
    endedAt: start.add(const Duration(hours: 1)),
    points: const [EpisodePoint('A real point')],
  )
];
Episode episode(
        {bool live = false,
        List<ServerConversation> members = const [],
        List<EpisodeMoment>? moments,
        DateTime? closedAt}) =>
    Episode(
      id: 'e',
      live: live,
      startedAt: start,
      lastActivityAt: start.add(const Duration(hours: 3)),
      closedAt: closedAt,
      moments: moments ?? composedMoments,
      conversationIds: const ['a', 'b'],
      members: members,
      title: 'Evening planning',
      emoji: '📝',
    );

void main() {
  for (final live in [false, true]) {
    test('processing owns one episode slot with live=$live, even before retained metadata arrives', () {
      final a = conversation('a');
      final b = conversation('b');
      final e = episode(live: live);
      final rows =
          buildHomeRows([conversation('later', hours: 4), a], [e], enabled: true, processingConversations: [a, b]);
      expect(rows.map((r) => r.conversation.id), ['later', 'episode:e']);
      expect(rows.last.isProcessing, isTrue);
      expect(rows.last.startedAt, e.startedAt);
      expect(rows.last.episodeConversationIds, {'a', 'b'});
      expect(buildHomeRows([], [e], enabled: true, processingConversations: [b]).single.isProcessing, isTrue);
    });
  }
  test('deleted pending member cannot hold a retained episode in processing', () {
    final a = conversation('a');
    final b = conversation('b');
    final rows = buildHomeRows(
        [a],
        [
          episode(members: [a, b])
        ],
        enabled: true,
        deletedIds: {'b'},
        processingConversations: [b]);
    expect(rows.single.conversation, same(a));
    expect(rows.single.isProcessing, isFalse);
  });
  for (final hasMetadata in [false, true]) {
    test('discarded pending member releases retained rows with metadata=$hasMetadata', () {
      final a = conversation('a');
      final pendingB = conversation('b');
      final closing = episode();
      final processing = buildHomeRows([a], [closing], enabled: true, processingConversations: [pendingB]);
      expect(processing.single.isProcessing, isTrue);

      // The server has retained only a, or the local processing entry learned
      // that b was discarded before retained metadata arrived.
      final reconciled = hasMetadata ? episode(members: [a]) : closing;
      final stalePending = hasMetadata ? pendingB : conversation('b', discarded: true);
      for (final pending in [
        <ServerConversation>[stalePending],
        <ServerConversation>[]
      ]) {
        final rows = buildHomeRows([a], [reconciled], enabled: true, processingConversations: pending);
        expect(rows.single.isProcessing, isFalse);
        expect(rows.single.conversation, same(a));
        expect(rows.single.episodeConversationIds, {'a', 'b'}, reason: 'Delete still owns full membership');
      }
    });
  }
  test('locally discarded pending member cannot override stale retained metadata', () {
    final a = conversation('a');
    final rows = buildHomeRows(
        [a],
        [
          episode(members: [a])
        ],
        enabled: true,
        processingConversations: [conversation('a', discarded: true)]);
    expect(rows.single.isProcessing, isFalse);
    expect(rows.single.conversation, same(a));
  });
  test('episodes off leaves processing outside the episode projection', () {
    final a = conversation('a');
    final rows = buildHomeRows([a], [episode()], enabled: false, processingConversations: [conversation('b')]);
    expect(rows.single.conversation, same(a));
    expect(rows.single.isProcessing, isFalse);
    expect(rows.single.episodeConversationIds, isEmpty);
  });

  test('multiple retained members become one episode row, without mutation', () {
    final a = conversation('a');
    final b = conversation('b', hours: 2);
    final rows = buildHomeRows([b, a], [episode()], enabled: true);
    expect(rows.length, 1);
    expect(rows.single.episode?.id, 'e');
    expect(rows.single.conversation.structured.title, 'Evening planning');
    expect(rows.single.conversation.structured.emoji, '📝');
    expect(a.structured.title, 'Title a');
    expect(rows.single.episode!.members, [a, b]);
  });
  test('one non-discarded member preserves the conversation object and destination', () {
    final a = conversation('a');
    final rows = buildHomeRows([conversation('b', discarded: true), a], [episode()], enabled: true);
    expect(rows.single.conversation, same(a));
    expect(rows.single.episode, isNull);
    expect(rows.single.episodeConversationIds, {'a', 'b'}, reason: 'processing members remain represented');
  });
  test('full deletion membership does not resurrect a stale locally retained discarded member', () {
    final a = conversation('a');
    final staleB = conversation('b');
    final rows = buildHomeRows([
      a,
      staleB
    ], [
      episode(members: [a])
    ], enabled: true);
    expect(rows.single.conversation, same(a));
    expect(rows.single.episodeConversationIds, {'a', 'b'});
  });
  test('all-discarded members leave no row', () {
    expect(
        buildHomeRows([conversation('a', discarded: true), conversation('b', discarded: true)], [episode()],
            enabled: true),
        isEmpty);
  });
  test('live membership keeps the existing visibility behavior', () {
    final unrelated = conversation('other');
    final rows = buildHomeRows([conversation('a'), unrelated], [episode(live: true)],
        enabled: true, liveConversationIds: {'a', 'b'});
    expect(rows.single.conversation, same(unrelated));
    expect(rows.single.episode, isNull);
  });
  test('episodes off preserves exact objects, order, and discarded rows', () {
    final input = [conversation('a'), conversation('b', discarded: true)];
    final rows = buildHomeRows(input, [episode()], enabled: false, liveConversationIds: {'a'});
    expect(rows.map((r) => r.conversation), input);
    expect(rows.every((r) => r.episode == null), isTrue);
  });
  test('10 PM–1 AM episode groups on its local start day and sorts by start', () {
    final rows = buildHomeRows(
        [conversation('a'), conversation('b', hours: 2), conversation('later', hours: 4)], [episode()],
        enabled: true);
    expect(rows.first.conversation.id, 'later');
    expect(rows.last.day, DateTime(2026, 10, 29));
    expect(rows.last.startedAt, start);
  });
  test('unloaded members use API metadata rather than turning a partial page into a single', () {
    final a = conversation('a');
    final b = conversation('b', hours: 2);
    final rows = buildHomeRows([
      a
    ], [
      episode(members: [a, b])
    ], enabled: true);
    expect(rows.single.episode!.members.length, 2);
  });
  test('local deletion/discard wins over stale server metadata, undo restores grouping', () {
    final a = conversation('a');
    final b = conversation('b');
    final e = episode(members: [a, b]);
    expect(buildHomeRows([a], [e], enabled: true, deletedIds: {'b'}).single.episode, isNull);
    expect(buildHomeRows([a, b], [e], enabled: true).single.episode, isNotNull);
  });
  test('blank title and emoji fall back to the first retained member', () {
    final e = Episode(
        moments: composedMoments,
        id: 'e',
        live: false,
        startedAt: start,
        lastActivityAt: start,
        conversationIds: ['a', 'b']);
    final row = buildHomeRows([conversation('a'), conversation('b')], [e], enabled: true).single;
    expect(row.conversation.structured.title, 'Title a');
    expect(row.conversation.structured.emoji, '☕');
  });

  group('closed episode waiting for its summary', () {
    final closed = start.add(const Duration(hours: 3));
    List<HomeRow> rows(Duration sinceClose, {List<EpisodeMoment> moments = const [], Set<String> live = const {}}) {
      final a = conversation('a');
      final b = conversation('b', hours: 2);
      return buildHomeRows([b, a], [episode(moments: moments, closedAt: closed)],
          enabled: true, liveConversationIds: live, now: closed.add(sinceClose));
    }

    test('holds on processing, never exposing draft notes', () {
      final held = rows(const Duration(minutes: 14)).single;
      expect(held.isProcessing, isTrue);
      expect(held.episode?.id, 'e', reason: 'the row opens the same page throughout');
      expect(held.conversation.id, 'episode:e');
      expect(held.episodeConversationIds, {'a', 'b'});
    });
    test('the summary landing ends the hold at once', () {
      final done = rows(const Duration(minutes: 1), moments: composedMoments).single;
      expect(done.isProcessing, isFalse);
      expect(done.episode?.id, 'e');
    });
    test('a summary that never lands keeps the one row', () {
      final row = rows(Episode.summaryWait).single;
      expect(row.conversation.id, 'episode:e');
      expect(row.isProcessing, isFalse);
      expect(row.episode?.id, 'e');
    });
    test('notes alone do not count as a summary', () {
      final notesOnly = [
        EpisodeMoment(id: 'm', conversationId: 'a', startedAt: start, endedAt: start, heading: 'Draft')
      ];
      expect(rows(const Duration(minutes: 1), moments: notesOnly).single.isProcessing, isTrue);
    });
    test('an episode closed locally before the server says so counts from its last activity', () {
      final a = conversation('a');
      final b = conversation('b', hours: 2);
      final row = buildHomeRows([b, a], [episode(moments: const [])],
              enabled: true, now: closed.add(const Duration(minutes: 1)))
          .single;
      expect(row.isProcessing, isTrue);
    });
    test('one member is unaffected: it already opens its own conversation', () {
      final a = conversation('a');
      final row = buildHomeRows([conversation('b', discarded: true), a], [episode(moments: const [], closedAt: closed)],
              enabled: true, now: closed)
          .single;
      expect(row.conversation, same(a));
      expect(row.isProcessing, isFalse);
    });
  });
}
