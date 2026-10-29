import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';

final _t0 = DateTime.utc(2026, 10, 20, 12);

Episode _episode({String id = 'ep1', bool live = true, List<EpisodeItem> items = const []}) => Episode(
      id: id,
      live: live,
      startedAt: _t0,
      lastActivityAt: _t0,
      title: 'Lunch plans',
      items: items,
      conversationIds: const ['c1', 'c2'],
    );

EpisodeItem _item(String id) => EpisodeItem(id: id, text: 'Book the table', createdAt: _t0);

class _HomeHistory extends ConversationProvider {
  _HomeHistory() : super(isSignedIn: () => false);
  void changed() => notifyListeners();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('Home collects every page, including empty filtered pages, before publishing membership', () async {
    final cursorCalls = <String?>[];
    final lastPage = Completer<ApiResult<EpisodePageRead>>();
    final provider = EpisodeProvider(fetchPage: (from, to, {cursor}) async {
      cursorCalls.add(cursor);
      if (cursor == null) return const ApiSuccess(EpisodePageRead(enabled: true, nextCursor: 'page-2'));
      return lastPage.future;
    })
      ..debugSetLive(null);
    addTearDown(provider.dispose);
    final reading = provider.refreshHome(_t0, _t0.add(const Duration(days: 1)));
    await Future<void>.delayed(Duration.zero);
    expect(cursorCalls, [null, 'page-2']);
    expect(provider.homeEpisodes, isEmpty);
    lastPage.complete(ApiSuccess(EpisodePageRead(enabled: true, episodes: [_episode(live: false)])));
    await reading;
    expect(provider.homeEpisodes.single.id, 'ep1');
    await provider.refreshHome(_t0, _t0.add(const Duration(days: 1)));
    expect(cursorCalls.length, 2, reason: 'rebuilds coalesce within the poll interval');
  });

  for (final close in ['poll', 'finalize', 'wrapUp']) {
    test('Home refreshes immediately after close via $close and fences a stale in-flight read', () async {
      var closed = false;
      var reads = 0;
      final stale = Completer<ApiResult<EpisodePageRead>>();
      final provider = EpisodeProvider(
        clock: () => _t0,
        fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: closed ? null : _episode())),
        lookup: (_) async => ApiSuccess(EpisodeRead(enabled: true, episode: _episode(live: false))),
        wrapUp: (_, {conversationId}) async => ApiSuccess(_episode(live: false)),
        fetchPage: (from, to, {cursor}) async {
          reads++;
          if (reads == 2) return stale.future;
          return ApiSuccess(EpisodePageRead(enabled: true, episodes: [_episode(live: !closed)]));
        },
      );
      addTearDown(provider.dispose);
      await provider.refreshLive();
      await provider.refreshHome(_t0, _t0);
      expect(provider.homeEpisodes.single.live, isTrue);
      final inFlight = provider.refreshHome(_t0, _t0, force: true);
      await Future<void>.delayed(Duration.zero);
      closed = true;
      switch (close) {
        case 'poll':
          await provider.refreshLive();
        case 'finalize':
          provider.onLiveFinalized();
        case 'wrapUp':
          await provider.wrapUp();
      }
      expect(provider.homeEpisodes.single.live, isFalse, reason: 'no individual-row flash while revalidating');
      await provider.refreshHome(_t0, _t0);
      expect(reads, 3, reason: 'close bypasses the 30-second Home cache');
      stale.complete(ApiSuccess(EpisodePageRead(enabled: true, episodes: [_episode()])));
      await inFlight;
      expect(provider.homeEpisodes.single.live, isFalse);
      expect(provider.live, isNull);
    });
  }

  test('disabled episodes never request Home history', () async {
    final provider = EpisodeProvider(fetchPage: (from, to, {cursor}) async => throw StateError('not admitted'));
    addTearDown(provider.dispose);
    await provider.refreshHome(_t0, _t0);
    expect(provider.homeEpisodes, isEmpty);
  });

  test('an account switch rejects an old Home response and hides cached episodes immediately', () async {
    SharedPreferencesUtil().uid = 'first';
    final response = Completer<ApiResult<EpisodePageRead>>();
    final provider = EpisodeProvider(fetchPage: (from, to, {cursor}) => response.future)
      ..debugSetLive(null)
      ..debugSetHomeEpisodes([_episode(live: false)]);
    addTearDown(provider.dispose);
    final reading = provider.refreshHome(_t0, _t0);
    SharedPreferencesUtil().uid = 'second';
    expect(provider.enabled, isFalse);
    expect(provider.homeEpisodes, isEmpty);
    response.complete(ApiSuccess(EpisodePageRead(enabled: true, episodes: [_episode(live: false)])));
    await reading;
    expect(provider.homeEpisodes, isEmpty);
  });

  test('a failed later page preserves the last complete Home snapshot', () async {
    final provider = EpisodeProvider(
        fetchPage: (from, to, {cursor}) async => cursor == null
            ? ApiSuccess(EpisodePageRead(enabled: true, episodes: [_episode(id: 'partial')], nextCursor: 'next'))
            : const ApiFailure(ApiProblem(ApiProblemKind.transport)))
      ..debugSetLive(null)
      ..debugSetHomeEpisodes([_episode(id: 'complete', live: false)]);
    addTearDown(provider.dispose);
    await provider.refreshHome(_t0, _t0);
    expect(provider.homeEpisodes.single.id, 'complete');
  });

  test('local member deletion stays hidden after DELETE settles, while Undo restores it', () async {
    final member = ServerConversation(id: 'c1', createdAt: _t0, structured: Structured('Member', ''));
    final history = _HomeHistory()..conversations = [member];
    final episodes = EpisodeProvider()..debugSetLive(null);
    addTearDown(history.dispose);
    addTearDown(episodes.dispose);
    episodes.observeHomeConversations(history);
    history.memoriesToDelete['c1'] = member;
    history.conversations = [];
    history.changed();
    expect(episodes.hiddenHomeMembers, {'c1'});
    history.memoriesToDelete.clear();
    history.changed();
    expect(episodes.hiddenHomeMembers, {'c1'}, reason: 'stale episode metadata cannot resurrect a deleted member');
    history.conversations = [member];
    history.changed();
    expect(episodes.hiddenHomeMembers, isEmpty, reason: 'Undo or a refused DELETE restores membership');
  });

  test('cold launch recovers an idle-closed episode from the account-scoped live pointer', () async {
    SharedPreferencesUtil().uid = 'account-a';
    final first = EpisodeProvider(fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: _episode())));
    await first.refreshLive();
    first.dispose();
    final ids = <String>[];
    final restored = EpisodeProvider(
      clock: () => _t0,
      fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
      lookup: (id) async {
        ids.add(id);
        return ApiSuccess(EpisodeRead(enabled: true, episode: _episode(live: false)));
      },
    );
    addTearDown(restored.dispose);
    await restored.refreshLive();
    await Future<void>.delayed(Duration.zero);
    expect(ids, ['c2']);
    expect(restored.previous?.id, 'ep1');
    SharedPreferencesUtil().uid = 'account-b';
    expect(restored.previous, isNull);
    await restored.refreshLive();
    expect(restored.previous, isNull);
    expect(ids, ['c2'], reason: 'another account never reads the saved member pointer');
  });

  test('a 404 means this server has no episodes and keeps today\'s UI', () async {
    final provider = EpisodeProvider(fetchLive: () async => const ApiFailure(ApiProblem(ApiProblemKind.notFound)));
    addTearDown(provider.dispose);
    await provider.refreshLive();
    expect(provider.enabled, isFalse);
    expect(provider.live, isNull);
    expect(provider.liveConversationIds, isEmpty);
  });

  test('a live read shows the episode and the conversations it stands for', () async {
    final provider = EpisodeProvider(
      fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: _episode())),
    );
    addTearDown(provider.dispose);
    await provider.refreshLive();
    expect(provider.enabled, isTrue);
    expect(provider.live?.id, 'ep1');
    expect(provider.liveConversationIds, {'c1', 'c2'});
  });

  test('a disabled answer hides the live episode even if one is sent', () async {
    final provider = EpisodeProvider(
      fetchLive: () async => ApiSuccess(EpisodeRead(enabled: false, episode: _episode())),
    );
    addTearDown(provider.dispose);
    await provider.refreshLive();
    expect(provider.enabled, isFalse);
    expect(provider.liveConversationIds, isEmpty);
  });

  test('a failed read keeps what was shown', () async {
    var fail = false;
    final provider = EpisodeProvider(
      fetchLive: () async => fail
          ? const ApiFailure(ApiProblem(ApiProblemKind.transport))
          : ApiSuccess(EpisodeRead(enabled: true, episode: _episode())),
    );
    addTearDown(provider.dispose);
    await provider.refreshLive();
    fail = true;
    await provider.refreshLive();
    expect(provider.live?.id, 'ep1');
    expect(provider.enabled, isTrue);
  });

  test('wrap up with a conversation clears the live episode at once', () async {
    String? sentConversation;
    final provider = EpisodeProvider(
      wrapUp: (id, {conversationId}) async {
        sentConversation = conversationId;
        return ApiSuccess(_episode(id: id));
      },
    );
    addTearDown(provider.dispose);
    provider.debugSetLive(_episode());
    expect(await provider.wrapUp(conversationId: 'c2'), isTrue);
    expect(sentConversation, 'c2');
    expect(provider.live, isNull);
    expect(provider.wrappingUp, isFalse);
  });

  test('a failed wrap up keeps the live episode', () async {
    final provider = EpisodeProvider(
      wrapUp: (id, {conversationId}) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    );
    addTearDown(provider.dispose);
    provider.debugSetLive(_episode());
    expect(await provider.wrapUp(conversationId: 'c2'), isFalse);
    expect(provider.live?.id, 'ep1');
  });

  test('undo hides a captured item at once and restores it if the server refuses', () async {
    var ok = false;
    final provider = EpisodeProvider(
      dismiss: (id, itemId) async => ok
          ? ApiSuccess(_episode(items: [_item(itemId).withStatus(EpisodeItemStatus.dismissed)]))
          : const ApiFailure(ApiProblem(ApiProblemKind.transport)),
    );
    addTearDown(provider.dispose);
    provider.debugSetLive(_episode(items: [_item('i1')]));

    final failed = provider.dismissItem('i1');
    expect(provider.live!.visibleItems, isEmpty, reason: 'hidden before the server answers');
    expect(await failed, isFalse);
    expect(provider.live!.visibleItems.single.id, 'i1');

    ok = true;
    expect(await provider.dismissItem('i1'), isTrue);
    expect(provider.live!.visibleItems, isEmpty);
  });

  test('a conversation\'s episode is read once and cached', () async {
    var calls = 0;
    final provider = EpisodeProvider(
      lookup: (conversationId) async {
        calls++;
        return ApiSuccess(EpisodeRead(enabled: true, episode: _episode(live: false)));
      },
    );
    addTearDown(provider.dispose);
    final results = await Future.wait([provider.episodeFor('c1'), provider.episodeFor('c1')]);
    expect(results.map((e) => e?.id), ['ep1', 'ep1']);
    expect(await provider.episodeFor('c1'), isNotNull);
    expect(calls, 1);
    expect(provider.cachedEpisodeFor('c1')?.live, isFalse);
  });

  test('a null live response retains the snapshot and refreshes closure through its member', () async {
    Episode? live = _episode();
    final provider = EpisodeProvider(
      clock: () => _t0,
      fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: live)),
      lookup: (_) async => ApiSuccess(EpisodeRead(enabled: true, episode: _episode(live: false))),
    );
    addTearDown(provider.dispose);
    await provider.refreshLive();
    live = null;
    await provider.refreshLive();
    await Future<void>.delayed(Duration.zero);
    expect(provider.live, isNull);
    expect(provider.previous?.id, 'ep1');
    expect(provider.previous?.live, isFalse);
    expect(provider.liveConversationIds, isEmpty);
    expect(provider.cachedEpisodeFor('c2')?.live, isFalse);
  });

  test('failed closure lookup keeps the prior title and member reachable', () async {
    final provider = EpisodeProvider(
      fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
      lookup: (_) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)),
      clock: () => _t0,
    )..debugSetLive(_episode());
    addTearDown(provider.dispose);
    await provider.refreshLive();
    expect(provider.previous?.title, 'Lunch plans');
    expect(provider.previous?.conversationIds, ['c1', 'c2']);
    expect(provider.notesUnavailable(), isTrue);
  });

  test('repeated successful reads cannot hide stale server notes', () async {
    var time = _t0;
    final provider = EpisodeProvider(
      clock: () => time,
      fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: _episode())),
    );
    addTearDown(provider.dispose);
    await provider.refreshLive();
    expect(provider.notesUnavailable(), isFalse);
    time = time.add(EpisodeProvider.notesStaleLimit);
    await provider.refreshLive();
    expect(provider.notesUnavailable(), isTrue);
  });

  test('a slow old closure lookup cannot replace a newer previous episode', () async {
    final provider = EpisodeProvider(
      clock: () => _t0,
      lookup: (_) async => ApiSuccess(EpisodeRead(enabled: true, episode: _episode(live: false))),
    );
    addTearDown(provider.dispose);
    final newer = Episode(id: 'newer', live: false, startedAt: _t0.add(const Duration(hours: 1)), lastActivityAt: _t0);
    provider.debugSetLive(newer);
    await provider.recoverPrevious('c1');
    expect(provider.previous?.id, 'newer');
  });

  test('the previous link retires once the closed episode is stale', () async {
    final staleAt = _t0.subtract(EpisodeProvider.previousExpiry + const Duration(hours: 1));
    var serving = Episode(
      id: 'stale',
      live: false,
      startedAt: staleAt,
      lastActivityAt: staleAt,
      conversationIds: const ['c1'],
    );
    final provider = EpisodeProvider(
      clock: () => _t0,
      lookup: (_) async => ApiSuccess(EpisodeRead(enabled: true, episode: serving)),
    );
    addTearDown(provider.dispose);
    await provider.recoverPrevious('c1');
    expect(provider.previous, isNull, reason: 'a long-closed episode is not offered from Home');

    serving = _episode(live: false);
    await provider.recoverPrevious('c2');
    expect(provider.previous?.id, 'ep1', reason: 'a recently closed one still is');
  });

  test('a quiet live poll does not re-read the recovery pointers every time', () async {
    SharedPreferencesUtil().uid = 'account-a';
    await SharedPreferencesUtil().saveString('lastLiveEpisodeConversation:account-a', 'c2');
    var time = _t0;
    var lookups = 0;
    final provider = EpisodeProvider(
      clock: () => time,
      fetchLive: () async => const ApiSuccess(EpisodeRead(enabled: true)),
      lookup: (_) async {
        lookups++;
        return const ApiSuccess(EpisodeRead(enabled: true));
      },
    );
    addTearDown(provider.dispose);
    await provider.refreshLive();
    await Future<void>.delayed(Duration.zero);
    expect(lookups, 1);
    await provider.refreshLive();
    await provider.refreshLive();
    await Future<void>.delayed(Duration.zero);
    expect(lookups, 1, reason: 'pointer recovery is throttled while quiet');
    time = time.add(EpisodeProvider.recoveryRetryInterval);
    await provider.refreshLive();
    await Future<void>.delayed(Duration.zero);
    expect(lookups, 2);
  });

  test('a recovered snapshot cannot hide finalization when member details open', () async {
    var time = _t0;
    var lookups = 0;
    final finalized = Episode(
      id: 'ep1',
      live: false,
      startedAt: _t0,
      lastActivityAt: _t0,
      bullets: const ['Finalized note'],
      conversationIds: const ['c1', 'c2'],
    );
    final provider = EpisodeProvider(
      clock: () => time,
      lookup: (_) async {
        lookups++;
        return ApiSuccess(EpisodeRead(enabled: true, episode: lookups == 1 ? _episode(live: false) : finalized));
      },
    );
    addTearDown(provider.dispose);
    await provider.recoverPrevious('c1');
    provider.debugSetLive(_episode(id: 'ep2'));
    expect(provider.cachedEpisodeFor('c1')?.bullets, isEmpty);
    expect(lookups, 1);
    expect((await provider.episodeFor('c1'))?.bullets, ['Finalized note']);
    expect(lookups, 2);
    expect((await provider.episodeFor('c1'))?.bullets, ['Finalized note']);
    expect(lookups, 2, reason: 'fresh detail reads still coalesce and cache');
    time = time.add(EpisodeProvider.episodeCacheTtl);
    await provider.episodeFor('c1');
    expect(lookups, 3, reason: 'even detail snapshots have a bounded lifetime');
  });

  test('item status parsing hides dropped and dismissed items', () {
    final items = [
      _item('a'),
      _item('b').withStatus(EpisodeItemStatus.kept),
      _item('c').withStatus(EpisodeItemStatus.dropped),
      _item('d').withStatus(EpisodeItemStatus.dismissed),
    ];
    expect(_episode(items: items).visibleItems.map((i) => i.id), ['a', 'b']);
  });
}
