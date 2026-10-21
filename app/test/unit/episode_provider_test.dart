import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/providers/episode_provider.dart';

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

void main() {
  test('a 404 means this server has no episodes and keeps today\'s UI', () async {
    final provider = EpisodeProvider(fetchLive: () async => const ApiFailure(ApiProblem(ApiProblemKind.notFound)));
    addTearDown(provider.dispose);
    await provider.refreshLive();
    expect(provider.enabled, isFalse);
    expect(provider.live, isNull);
    expect(provider.liveConversationIds, isEmpty);
  });

  test('a live read shows the episode and the conversations it stands for', () async {
    final provider =
        EpisodeProvider(fetchLive: () async => ApiSuccess(EpisodeRead(enabled: true, episode: _episode())));
    addTearDown(provider.dispose);
    await provider.refreshLive();
    expect(provider.enabled, isTrue);
    expect(provider.live?.id, 'ep1');
    expect(provider.liveConversationIds, {'c1', 'c2'});
  });

  test('a disabled answer hides the live episode even if one is sent', () async {
    final provider =
        EpisodeProvider(fetchLive: () async => ApiSuccess(EpisodeRead(enabled: false, episode: _episode())));
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
