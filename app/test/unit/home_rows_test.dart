import 'package:omi/utils/conversations/home_member_fallback.dart';
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

ServerConversation waiting(String id, int minute,
        {bool locked = false, ConversationStatus status = ConversationStatus.completed}) =>
    ServerConversation(
      id: id,
      createdAt: start.add(Duration(minutes: minute)),
      startedAt: start.add(Duration(minutes: minute)),
      finishedAt: start.add(Duration(minutes: minute + 1)),
      structured: Structured('', ''),
      isLocked: locked,
      status: status,
    );

void main() {
  test('capture stopped with a stale live snapshot retains completed members', () {
    final members = [conversation('a'), conversation('b')];
    final rows =
        buildHomeRows(members, [episode(live: true, members: members)], enabled: true, groupAwaitingTranscript: true);
    expect(rows, hasLength(1));
    expect(rows.single.episodeConversationIds, {'a', 'b'});
  });

  for (final processingCount in [0, 3]) {
    test('live snapshot owns every member with $processingCount processing recordings', () {
      final members = [for (var i = 0; i < 3; i++) waiting('closed-$i', i, status: ConversationStatus.processing)];
      final e = Episode(
          id: 'live',
          live: true,
          startedAt: start,
          lastActivityAt: start.add(const Duration(minutes: 10)),
          conversationIds: ['current', ...members.map((m) => m.id)],
          members: members);
      final rows = buildHomeRows(members, [e],
          enabled: true,
          liveConversationIds: {'current'},
          processingConversations: members.take(processingCount).toList(),
          groupAwaitingTranscript: true);
      // The screen inserts exactly one Listening row outside this projection.
      expect(rows, isEmpty);
    });
  }

  test('live episode identity owns disjoint live and Home member snapshots', () {
    final members = [for (var i = 0; i < 3; i++) waiting('closed-$i', i, status: ConversationStatus.processing)];
    final e = Episode(
        id: 'live',
        live: true,
        startedAt: start,
        lastActivityAt: start.add(const Duration(minutes: 10)),
        conversationIds: members.map((m) => m.id).toList(),
        members: members);
    final rows = buildHomeRows(members, [e],
        enabled: true,
        liveEpisodeId: 'live',
        liveConversationIds: {'current'},
        processingConversations: members,
        groupAwaitingTranscript: true);
    expect(rows, isEmpty);
  });

  test('closed episode still composing keeps its Processing row', () {
    final members = [for (var i = 0; i < 3; i++) waiting('closed-$i', i, status: ConversationStatus.processing)];
    final e = Episode(
        id: 'closed',
        live: false,
        startedAt: start,
        lastActivityAt: start.add(const Duration(minutes: 10)),
        closedAt: start.add(const Duration(minutes: 10)),
        conversationIds: members.map((m) => m.id).toList(),
        members: members);
    final rows =
        buildHomeRows(members, [e], enabled: true, processingConversations: members, groupAwaitingTranscript: true);
    expect(rows, hasLength(1));
    expect(rows.single.isProcessing, isTrue);
    expect(rows.single.count, 3);
  });

  test('deadline layout takes live-to-ended status from the latest episode', () {
    final a = conversation('a'), b = conversation('b');
    final cached = episode(live: true, members: [a, b]);
    final held = HomeEpisodeLayout([cached]);
    final ended = episode(members: [a, b], closedAt: start.add(const Duration(hours: 3)));
    final projection = held.apply([ended], standaloneIds: {});
    expect(projection.single.live, isFalse, reason: 'ending is a status update, not a refresh boundary');
    expect(projection.single.closedAt, ended.closedAt);
    expect(projection.single.startedAt, cached.startedAt);
    expect(projection.single.conversationIds, cached.conversationIds);
    expect(held.apply([], standaloneIds: {}).single.live, isFalse,
        reason: 'a later omitted snapshot must not revert an ended episode to live');
  });

  test('deadline layout admits a new recording without absorbing an existing source row', () {
    final old = conversation('old', hours: -1);
    final a = conversation('a'), b = conversation('b');
    final held = HomeEpisodeLayout([]);
    final added = episode(members: [a, b]);
    final projection = held.apply([added], standaloneIds: {'old'});
    final rows = buildHomeRows([old], projection, enabled: true);
    expect(rows.map((row) => row.conversation.id), ['episode:e', 'old']);
    expect(rows.first.episodeConversationIds, {'a', 'b'});
  });

  test('deadline layout rejects absorption through full IDs or member metadata and pins admitted recordings', () {
    final old = conversation('old', hours: -1), a = conversation('a'), b = conversation('b');
    final held = HomeEpisodeLayout([]);
    Episode candidate(String id, List<String> ids, List<ServerConversation> members) => Episode(
        id: id,
        live: false,
        startedAt: start,
        lastActivityAt: start,
        title: id,
        conversationIds: ids,
        members: members,
        moments: composedMoments);
    final absorbsFullId = candidate('full-id', ['a', 'old'], [a]);
    final absorbsMetadata = candidate('metadata', ['a'], [a, old]);
    final added = candidate('safe', ['a', 'b'], [a, b]);
    final projection = held.apply([absorbsFullId, absorbsMetadata, added], standaloneIds: {'old'});
    expect(projection.map((e) => e.id), ['safe']);
    final changed = candidate('safe', ['a', 'b', 'old'], [a, b, old]);
    final updated = held.apply([changed], standaloneIds: {'old'});
    expect(updated.single.conversationIds, ['a', 'b'], reason: 'an admitted episode also keeps its painted membership');
    expect(updated.single.members.map((m) => m.id), ['a', 'b']);
    final rows = buildHomeRows([old], updated, enabled: true);
    expect(rows.map((row) => row.conversation.id), ['episode:safe', 'old']);
  });

  test('deadline layout keeps membership and order while episode title and processing status update', () {
    final a = conversation('a');
    final b = conversation('b', hours: 1);
    final c = conversation('c', hours: 2);
    final cached = episode(members: [a, b], moments: [], closedAt: start);
    final held = HomeEpisodeLayout([cached]);
    final latest = Episode(
      id: cached.id,
      live: false,
      startedAt: start.add(const Duration(hours: 3)),
      lastActivityAt: start.add(const Duration(hours: 4)),
      title: 'Composed title arrived',
      members: [a, b, c],
      conversationIds: [a.id, b.id, c.id],
      moments: composedMoments,
    );
    final lateNewEpisode = Episode(
      id: 'new',
      live: false,
      startedAt: start,
      lastActivityAt: start,
      conversationIds: [c.id],
      members: [c],
    );
    List<HomeRow> rows(List<Episode> projection) => buildHomeRows([a, b, c], projection,
        enabled: true, finishingTitle: 'Finishing up…', now: start.add(const Duration(minutes: 1)));
    final before = rows(held.apply([cached], standaloneIds: {'c'}));
    final after = rows(held.apply([latest, lateNewEpisode], standaloneIds: {'c'}));
    expect(before.map((row) => row.conversation.id), ['c', 'episode:e']);
    expect(after.map((row) => row.conversation.id), before.map((row) => row.conversation.id));
    expect(after.map((row) => row.startedAt), before.map((row) => row.startedAt));
    expect(before.last.isProcessing, isTrue);
    expect(after.last.isProcessing, isFalse, reason: 'composition status updates in place');
    expect(after.last.conversation.structured.title, 'Composed title arrived');
    expect(after.last.episodeConversationIds, {'a', 'b'});
    expect(after.last.episode!.members.map((member) => member.id), ['a', 'b']);
    expect(held.apply([], standaloneIds: {'c'}).single, isNotNull,
        reason: 'an omitted episode cannot remove a painted row');
    expect(latest.members.length, 3, reason: 'the provider snapshot is never mutated');
  });

  test('adjacent unfinished captures fold into one Processing row with every member reachable', () {
    final a = waiting('a', 0), b = waiting('b', 2), old = waiting('old', -20);
    final rows =
        buildHomeRows([a, b, old], [], enabled: false, groupAwaitingTranscript: true, processingTitle: 'Processing');
    expect(rows.single.conversation.structured.title, 'Processing');
    expect(rows.single.episode!.members.map((m) => m.id).toSet(), {'a', 'b', 'old'});
    expect(rows.single.episodeConversationIds, {'a', 'b', 'old'});
    expect(rows.single.step, HomeStep.transcribing);
    expect(rows.single.count, 3);
    expect(buildHomeRows([a, b], [], enabled: false).map((r) => r.conversation.id), ['a', 'b'],
        reason: 'filtered views keep exact source matches');
  });
  test('awaiting speech stays in its episode after the summary deadline', () {
    final a = waiting('a', 0), b = waiting('b', 2);
    final rows = buildHomeRows([
      a,
      b
    ], [
      episode(members: [a, b], moments: [], closedAt: start)
    ],
        enabled: true,
        now: start.add(const Duration(days: 1)),
        finishingTitle: 'Finishing up…',
        processingTitle: 'Processing',
        groupAwaitingTranscript: true);
    expect(rows.single.isProcessing, isTrue);
    expect(rows.single.conversation.structured.title, 'Finishing up…');
    expect(rows.single.episode!.members.length, 2);
  });
  test('ready and locked rows break Processing runs and remain ordinary; in-flight rows join them', () {
    final ready = conversation('ready');
    final locked = waiting('locked', 2, locked: true);
    final pending = waiting('pending', 3, status: ConversationStatus.processing);
    final rows = buildHomeRows([waiting('a', 0), ready, locked, pending], [],
        enabled: false, groupAwaitingTranscript: true, processingTitle: 'Processing');
    for (final c in [ready, locked]) {
      expect(rows.singleWhere((r) => r.conversation.id == c.id).conversation, same(c));
    }
    expect(rows.where((r) => r.isProcessing).expand((r) => r.episodeConversationIds).toSet(), {'a', 'pending'});
  });

  group('Home row contract (David 2026-11-05)', () {
    ServerConversation provisional(String id, int minute, {String title = 'Mm-hmm.', String? step}) =>
        ServerConversation(
          id: id,
          createdAt: start.add(Duration(minutes: minute)),
          startedAt: start.add(Duration(minutes: minute)),
          finishedAt: start.add(Duration(minutes: minute + 4)),
          structured: Structured(title, '', titleProvenance: 'server_minimum'),
          homeStep: step,
        );
    List<HomeRow> home(List<ServerConversation> list, {List<Episode> episodes = const []}) =>
        buildHomeRows(list, episodes,
            enabled: episodes.isNotEmpty,
            groupAwaitingTranscript: true,
            processingTitle: 'Processing',
            finishingTitle: 'Finishing up');

    test('stand-in titles never show as their own row', () {
      final rows = home([
        provisional('yeah', 0, title: 'Yeah.'),
        provisional('rec', -30, title: 'Recording · 9:38 AM'),
        conversation('real', hours: -2),
      ]);
      expect(rows.map((r) => r.conversation.structured.title), ['Processing', 'Title real']);
      expect(rows.first.step, HomeStep.writingNotes);
      expect(rows.first.count, 2);
    });

    test('server-classified noise never shows on Home, and ready rows are finished', () {
      final noise = provisional('noise', 0, title: 'Recording · 9:38 AM', step: 'noise');
      final ready = provisional('ready', -10, title: 'Real title', step: 'ready');
      final rows = home([noise, ready]);
      expect(rows.map((r) => r.conversation.id), ['ready']);
      expect(buildHomeRows([noise], [], enabled: false).single.conversation.id, 'noise',
          reason: 'filtered views and search keep exact matches');
    });

    test('a run shows its least advanced step', () {
      final rows = home([provisional('notes', 0), waiting('empty', -10)]);
      expect(rows.single.step, HomeStep.transcribing);
    });

    test('server home_step wins over local inference', () {
      final c = provisional('x', 0, step: 'transcribing');
      expect(homeStepOf(c), HomeStep.transcribing);
      final done = conversation('y');
      expect(homeStepOf(done), isNull);
    });

    test('projected failures remain separate terminal rows between processing runs', () {
      final rows = home([
        provisional('p', 0),
        provisional('f1', -10, step: 'failed'),
        provisional('f2', -20, step: 'failed'),
        provisional('p2', -30),
      ]);
      expect(rows.map((r) => r.isProcessing), [true, false, false, true]);
      expect(rows.map((r) => r.conversation.id), containsAll(['f1', 'f2']));
    });

    test('explicit failure wins over deferred and client processing metadata', () {
      for (final c in [
        ServerConversation(
            id: 'deferred',
            createdAt: start,
            structured: Structured('Processing', ''),
            homeStep: 'failed',
            processingDeferred: true),
        ServerConversation(
            id: 'client',
            createdAt: start,
            structured: Structured('Processing', ''),
            homeStep: 'failed',
            clientProcessing: {'stage': 'processing'}),
      ]) {
        expect(homeStepOf(c), HomeStep.failed);
        expect(home([c]).single.isProcessing, isFalse);
      }
    });

    test('failed episode members remain openable outside their episode', () {
      final failed = provisional('expired', 0, step: 'failed');
      final e = episode(members: [failed], moments: [], closedAt: start);
      final rows = home([failed], episodes: [e]);
      expect(rows.single.conversation.id, 'expired');
      expect(rows.single.episode, isNull);
      expect(rows.single.isProcessing, isFalse);
    });

    test('Listening owns projected failures until capture stops, including metadata-only members', () {
      final failed = provisional('expired', 0, step: 'failed');
      final e = episode(live: true, members: [failed], moments: []).copyWith(conversationIds: ['current', failed.id]);
      for (final byEpisodeId in [false, true]) {
        for (final conversations in [
          <ServerConversation>[],
          [failed]
        ]) {
          final rows = buildHomeRows(conversations, [e],
              enabled: true,
              liveEpisodeId: byEpisodeId ? e.id : null,
              liveConversationIds: byEpisodeId ? {} : {'current'},
              processingConversations: [failed],
              groupAwaitingTranscript: true);
          expect(rows, isEmpty, reason: 'Listening owns the failed member too');
          final stopped = home(conversations, episodes: [e]);
          expect(stopped.single.conversation.id, failed.id);
          expect(stopped.single.episode, isNull);
          expect(stopped.single.isProcessing, isFalse);
        }
      }
    });

    test('runs never cross a day boundary', () {
      final today = provisional('today', 0);
      final yesterday = provisional('yesterday', -24 * 60);
      expect(home([today, yesterday]).length, 2);
    });

    test('a finished row between unfinished ones keeps them as two runs', () {
      final rows = home([provisional('a', 0), conversation('done', hours: -1), provisional('b', -180)]);
      expect(rows.map((r) => r.isProcessing), [true, false, true]);
    });

    test('an episode still finishing joins an adjacent Processing run', () {
      final a = waiting('a', 0), b = waiting('b', 2);
      final e = episode(members: [a, b], moments: [], closedAt: start);
      final rows = home([a, b, provisional('later', 100)], episodes: [e]);
      expect(rows.single.isProcessing, isTrue);
      expect(rows.single.episodeConversationIds, containsAll(['a', 'b', 'later']));
    });

    test('summary-retryable classifies as failed (hidden on Home); locked stays its own row', () {
      final retry = ServerConversation(
          id: 'r', createdAt: start, startedAt: start, structured: Structured('Yeah.', ''), summaryRetryable: true);
      expect(homeStepOf(retry), HomeStep.failed);
      expect(home([retry]), isEmpty);
      expect(homeStepOf(waiting('l', 0, locked: true)), isNull);
    });
  });
  test('suppression acknowledges full loaded snapshots and keeps unknown or unsettled members visible', () {
    final source = conversation('a')
      ..starred = true
      ..folderId = 'folder';
    final held = acknowledgeLoadedHomeMembers({
      'e': [conversation('a'), conversation('unknown'), waiting('waiting', 0)],
      'locked-parent': [conversation('a'), waiting('locked', 1)],
      'locked-metadata': [conversation('a'), waiting('unknown-lock', 1, locked: true)],
    }, [
      source,
      waiting('waiting', 0),
      waiting('locked', 1, locked: true)
    ]);
    expect(held['e'], [same(source)]);
    expect(held.containsKey('locked-parent'), isFalse);
    expect(held.containsKey('locked-metadata'), isFalse);
    final restored = retainSuppressedHomeMembers([], {source.id: held['e']!.single}, ['a']).single;
    expect(restored.starred, isTrue);
    expect(restored.folderId, 'folder');
  });

  test('server omissions remain reachable when an overlay is replaced, on any page', () {
    final a = conversation('a');
    final b = conversation('b');
    final old = conversation('unfetched-older', hours: -300);
    final local = retainSuppressedHomeMembers([old], {'a': a, 'b': b}, ['a', 'b']);
    final loaded = buildHomeRows(
        local,
        [
          episode(members: [a, b])
        ],
        enabled: true);
    expect(loaded.map((r) => r.conversation.id), containsAll(['episode:e', old.id]));
    expect(loaded.any((r) => r.conversation.id == a.id), isFalse);
    final replaced = buildHomeRows(local, [], enabled: true);
    expect(replaced.map((r) => r.conversation.id).toSet(), {'a', 'b', old.id});
    expect(retainSuppressedHomeMembers([a, b], {'a': a}, ['a', 'unknown']).length, 2);
  });

  for (final live in [false, true]) {
    test('processing owns one episode slot with live=$live, even before retained metadata arrives', () {
      final a = conversation('a');
      final b = conversation('b');
      final e = episode(live: live, moments: const []);
      final rows =
          buildHomeRows([conversation('later', hours: 4), a], [e], enabled: true, processingConversations: [a, b]);
      expect(rows.map((r) => r.conversation.id), ['later', 'episode:e']);
      expect(rows.last.isProcessing, isTrue);
      expect(rows.last.startedAt, e.startedAt);
      expect(rows.last.episodeConversationIds, {'a', 'b'});
      expect(buildHomeRows([], [e], enabled: true, processingConversations: [b]).single.isProcessing, isTrue);
    });
  }
  test('a composed episode keeps its notes row while a member is still processing', () {
    // David's Home, 2026-11-06: "Code Review, Coffee, and a Game Platform" had notes, yet Home
    // showed "Finishing up… Writing notes · 3h 45m" because one member sat in the processing list.
    final a = conversation('a');
    final b = conversation('b', hours: 2);
    final rows = buildHomeRows(
        [a, b],
        [
          episode(members: [a, b])
        ],
        enabled: true,
        finishingTitle: 'Finishing up…',
        processingConversations: [b]);
    expect(rows.single.isProcessing, isFalse);
    expect(rows.single.conversation.id, 'episode:e');
    expect(rows.single.conversation.structured.title, 'Evening planning');
    expect(rows.single.episodeConversationIds, {'a', 'b'});
  });
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
      final closing = episode(moments: const []);
      final processing = buildHomeRows([a], [closing], enabled: true, processingConversations: [pendingB]);
      expect(processing.single.isProcessing, isTrue);

      // The server has retained only a, or the local processing entry learned
      // that b was discarded before retained metadata arrived.
      final reconciled = hasMetadata ? episode(members: [a], moments: const []) : closing;
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

  test('uncomposed episode never echoes the first member title', () {
    final a = conversation('a');
    final b = conversation('b');
    final e = episode(members: [a, b], moments: const [], closedAt: start);
    final row = buildHomeRows([a, b], [e],
            enabled: true, finishingTitle: 'Finishing up…', now: start.add(const Duration(minutes: 1)))
        .single;
    expect(row.conversation.structured.title, 'Finishing up…');
    expect(a.structured.title, 'Title a');
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
