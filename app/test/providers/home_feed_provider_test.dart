import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/home_feed_cache.dart';
import 'package:omi/backend/http/api/home_feed.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/home_feed.dart';
import 'package:omi/providers/home_feed_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

HomeFeedCard card(int i, {String kind = 'conversation', int age = 0}) => HomeFeedCard(
    id: '$kind:$i',
    kind: kind,
    detailId: '$i',
    startedAt: DateTime.utc(2026, 11, 15).subtract(Duration(days: age, minutes: i)),
    title: 'Title $i',
    emoji: '🧠',
    preview: 'Preview $i',
    status: 'completed',
    starred: false,
    isLocked: false,
    hasTasks: true,
    memberCount: kind == 'episode' ? 12 : 1,
    sources: const ['omi'],
    summaryAvailable: true,
    revision: 'source:r1');
ApiSuccess<HomeFeedPage> page(List<HomeFeedCard> cards,
        {String? cursor, bool more = false, bool partial = false, String generation = 'g1'}) =>
    ApiSuccess(
        HomeFeedPage(items: cards, nextCursor: cursor, hasMore: more, truncated: partial, generation: generation));

class MemoryCache extends HomeFeedCache {
  List<HomeFeedCard> value = [];
  @override
  Future<List<HomeFeedCard>> read(String owner) async => value;
  @override
  Future<void> write(String owner, List<HomeFeedCard> cards, bool Function() current) async {
    if (current()) value = List.of(cards);
  }
}

Future<void> flush() async {
  for (var i = 0; i < 15; i++) {
    await Future<void>.delayed(Duration.zero);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  test('API uses cursor feed; display seeds contain no transcript or membership', () async {
    final api = HomeFeedApi(
        baseUrl: 'https://fixture/',
        send: (request) async {
          expect(request.url, 'https://fixture/v1/home/feed?limit=50&cursor=opaque');
          return http.Response(
              jsonEncode({
                'items': [card(1, kind: 'episode').toJson()],
                'next_cursor': null,
                'has_more': false,
                'truncated': false,
                'generation': 'test-generation'
              }),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'});
        });
    final result = await api.page(cursor: 'opaque');
    expect(result, isA<ApiSuccess<HomeFeedPage>>());
    final c = (result as ApiSuccess<HomeFeedPage>).data.items.single;
    expect(c.displaySeed().transcriptSegments, isEmpty);
    expect(c.episodeSeed().conversationIds, isEmpty);
    expect(c.episodeSeed().members, isEmpty);
  });
  test('unknown recording origin keeps pagination order without inventing detail timing', () {
    final json = card(1).toJson()..['started_at'] = null;
    final unknown = HomeFeedCard.fromJson(json);
    expect(unknown.startedAt, isNull);
    expect(unknown.sortAt, card(1).sortAt);
    expect(unknown.displaySeed().startedAt, isNull);
    expect(unknown.withoutText().toJson()['started_at'], isNull);
    expect(unknown.toJson()['sort_at'], json['sort_at']);
  });
  test('cache paints before remote; refresh discards old pages', () async {
    final remote = Completer<ApiResult<HomeFeedPage>>();
    final cache = MemoryCache()..value = [card(99, age: 30)];
    final p = HomeFeedProvider(owner: () => 'a', cache: cache, fetch: ({cursor}) => remote.future);
    final started = p.start();
    await flush();
    expect(p.items.single.id, 'conversation:99');
    remote.complete(page([card(1, age: 8)]));
    await started;
    expect(p.items.map((c) => c.id), ['conversation:1']);
    expect(cache.value.map((c) => c.id), ['conversation:1']);
    p.dispose();
  });
  test('dense grouped history warms at most eight requests; continuation coalesces', () async {
    var calls = 0;
    Completer<ApiResult<HomeFeedPage>>? pending;
    final p = HomeFeedProvider(
        owner: () => 'a',
        cache: MemoryCache(),
        now: () => DateTime.utc(2026, 11, 15),
        fetch: ({cursor}) async {
          calls++;
          if (calls > 8) return (pending = Completer<ApiResult<HomeFeedPage>>()).future;
          return page([card(calls, kind: 'episode')], cursor: 'page-$calls', more: true);
        });
    await p.start();
    await flush();
    expect(calls, 8);
    expect(p.items, hasLength(8));
    final a = p.loadMore(), b = p.loadMore();
    expect(calls, 9);
    pending!.complete(page([card(9)]));
    await Future.wait([a, b]);
    expect(p.items, hasLength(9));
    expect(p.hasMore, false);
    p.dispose();
  });
  test('failed page retries same cursor; partial does not exhaust', () async {
    var calls = 0;
    final cursors = <String?>[];
    final p = HomeFeedProvider(
        owner: () => 'a',
        cache: MemoryCache(),
        now: () => DateTime.utc(2026, 11, 15),
        fetch: ({cursor}) async {
          cursors.add(cursor);
          calls++;
          if (calls == 1) return page([card(1, age: 8)], cursor: 'next', more: true);
          if (calls == 2) return const ApiFailure(ApiProblem(ApiProblemKind.server));
          return page([card(2, age: 9)], cursor: 'last', more: true, partial: true);
        });
    await p.start();
    await p.loadMore();
    expect(p.hasMore, true);
    expect(p.items, hasLength(1));
    await p.loadMore();
    expect(cursors, [null, 'next', 'next']);
    expect(p.hasMore, true);
    expect(p.partial, true);
    p.dispose();
  });
  test('account and filter fence stale result/cache', () async {
    var owner = 'a';
    final remote = Completer<ApiResult<HomeFeedPage>>();
    final cache = MemoryCache();
    final p = HomeFeedProvider(owner: () => owner, cache: cache, fetch: ({cursor}) => remote.future);
    final first = p.start();
    await flush();
    owner = 'b';
    p.setActive(false);
    remote.complete(page([card(1)]));
    await first;
    expect(p.items, isEmpty);
    expect(cache.value, isEmpty);
    p.dispose();
  });
  test('server outage is never compatible success', () async {
    final p = HomeFeedProvider(
        owner: () => 'a',
        cache: MemoryCache(),
        fetch: ({cursor}) async => const ApiFailure(ApiProblem(ApiProblemKind.server)));
    await p.start();
    expect(p.unsupported, false);
    expect(p.problem!.kind, ApiProblemKind.server);
    expect(p.partial, true);
    p.dispose();
  });
  for (final action in ['refresh', 'continuation', 'reconcile']) {
    test('serving rollback restores compatibility after adoption during $action', () async {
      var disabled = false;
      final p = HomeFeedProvider(
          owner: () => 'a',
          cache: MemoryCache(),
          now: () => DateTime.utc(2026, 11, 15),
          fetch: ({cursor}) async => disabled
              ? const ApiFailure(ApiProblem(ApiProblemKind.notFound, statusCode: 404))
              : page([card(1, age: 8)], cursor: 'next', more: true));
      await p.start();
      expect(p.items, hasLength(1));
      disabled = true;
      if (action == 'refresh') await p.refresh();
      if (action == 'continuation') await p.loadMore();
      if (action == 'reconcile') await p.reconcileLoadedWindow();
      expect(p.unsupported, true);
      expect(p.items, isEmpty);
      p.dispose();
    });
  }
  test('cache scoped per account and stale writer fenced', () async {
    final cache = HomeFeedCache();
    await cache.write('a', [card(1)], () => true);
    expect(await cache.read('b'), isEmpty);
    await cache.write('a', [card(2)], () => false);
    expect((await cache.read('a')).single.detailId, '1');
  });
  test('synchronous transport throw releases flight and permits retry', () async {
    var calls = 0;
    final p = HomeFeedProvider(
        owner: () => 'a',
        cache: MemoryCache(),
        fetch: ({cursor}) {
          calls++;
          if (calls == 1) throw const SocketException('offline fixture');
          return Future.value(page([card(1, age: 8)]));
        });
    await p.start();
    expect(p.loading, false);
    expect(p.problem!.kind, ApiProblemKind.transport);
    await p.refresh();
    expect(p.items, hasLength(1));
    expect(p.problem, null);
    p.dispose();
  });
  test('empty budget-limited pages advance cursor within warming cap', () async {
    var calls = 0;
    final p = HomeFeedProvider(
        owner: () => 'a',
        cache: MemoryCache(),
        fetch: ({cursor}) async {
          calls++;
          return calls < 3 ? page([], cursor: 'scan:$calls', more: true, partial: true) : page([card(1, age: 8)]);
        });
    await p.start();
    await flush();
    expect(calls, 3);
    expect(p.items, hasLength(1));
    expect(p.hasMore, false);
    p.dispose();
  });
  testWidgets('preparation fallback schedules at most three bounded idle calls', (tester) async {
    var calls = 0;
    final p = HomeFeedProvider(
        owner: () => 'a',
        cache: MemoryCache(),
        fetch: ({cursor}) async => const ApiFailure(
            ApiProblem(ApiProblemKind.rejected, statusCode: 409, detail: 'home_feed_preparation_required')),
        prepare: () async {
          calls++;
          return const ApiSuccess(HomeFeedPreparation(ready: false, processed: 10, hasMore: true));
        });
    await p.start();
    expect(p.unsupported, true);
    expect(calls, 0);
    // Three calls 5 s apart (the minimum spacing), then the 30 s idle pause.
    for (var i = 0; i < 12; i++) {
      await tester.pump(const Duration(seconds: 1));
    }
    expect(calls, 3);
    for (var i = 0; i < 25; i++) {
      await tester.pump(const Duration(seconds: 1));
    }
    expect(calls, 3, reason: 'the fourth call waits out the 30 s pause');
    p.dispose();
  });
  testWidgets('filter/account change cancels preparation', (tester) async {
    var calls = 0, owner = 'a';
    final p = HomeFeedProvider(
        owner: () => owner,
        cache: MemoryCache(),
        fetch: ({cursor}) async => const ApiFailure(
            ApiProblem(ApiProblemKind.rejected, statusCode: 409, detail: 'home_feed_preparation_required')),
        prepare: () async {
          calls++;
          return const ApiSuccess(HomeFeedPreparation(ready: false, processed: 10, hasMore: true));
        });
    await p.start();
    owner = 'b';
    p.setActive(false);
    await tester.pump(const Duration(seconds: 2));
    expect(calls, 0);
    expect(p.unsupported, false);
    expect(p.problem, null);
    p.dispose();
  });

  test('decodes fixture emitted by backend HomeFeedResponse model', () async {
    final json = jsonDecode(await File('test/fixtures/home_feed_page.json').readAsString()) as Map<String, dynamic>;
    final parsed = HomeFeedPage.fromJson(json);
    expect(parsed.items.single.revision, 'policy:source:opaque');
    expect(parsed.items.single.memberCount, 12);
    expect(parsed.items.single.sources, ['omi', 'desktop']);
  });
  test('remote generation change revalidates older cards absent from continuation', () async {
    var calls = 0;
    final p = HomeFeedProvider(
        owner: () => 'a',
        cache: MemoryCache(),
        fetch: ({cursor}) async {
          calls++;
          if (calls == 1) return page([card(1, age: 8)], cursor: 'old', more: true, generation: 'before-delete');
          if (calls == 2) return page([card(2, age: 9)], generation: 'after-delete');
          return page([card(3, age: 8)], generation: 'after-delete');
        });
    await p.start();
    await p.loadMore();
    await flush();
    expect(p.items.map((c) => c.id), ['conversation:3']);
    expect(calls, 3);
    p.dispose();
  });
  test('known pending source deletion removes source and redacts episode text in cache', () async {
    final cache = MemoryCache();
    final source = ConversationProvider(isSignedIn: () => false);
    final p = HomeFeedProvider(
        owner: () => 'a',
        cache: cache,
        fetch: ({cursor}) async => page([card(1, age: 8), card(2, kind: 'episode', age: 8)]))
      ..observeConversations(source);
    await p.start();
    source.homeCardSourceChanged!('1', true);
    await flush();
    expect(p.items.single.kind, 'episode');
    expect(p.items.single.title, isEmpty);
    expect(p.items.single.preview, isEmpty);
    expect(cache.value.single.title, isEmpty);
    p.dispose();
    expect(source.homeCardSourceChanged, null);
    source.dispose();
  });
  test('offline restart paints only redacted shells, never prior deleted or locked text', () async {
    final cache = HomeFeedCache();
    await cache.write('a', [card(1, age: 8)], () => true);
    final persisted = await cache.read('a');
    expect(persisted.single.title, isEmpty);
    expect(persisted.single.preview, isEmpty);
    final p = HomeFeedProvider(
        owner: () => 'a',
        cache: cache,
        fetch: ({cursor}) async => const ApiFailure(ApiProblem(ApiProblemKind.transport)));
    await p.start();
    expect(p.items.single.title, isEmpty);
    expect(p.items.single.preview, isEmpty);
    expect(p.problem!.kind, ApiProblemKind.transport);
    p.dispose();
  });
  testWidgets('remote dirty continuation redacts old text then reconciles after preparation', (tester) async {
    var calls = 0;
    final p = HomeFeedProvider(
        owner: () => 'a',
        cache: MemoryCache(),
        fetch: ({cursor}) async {
          calls++;
          if (calls == 1) return page([card(1, age: 8)], cursor: 'next', more: true, generation: 'before-delete');
          if (calls == 2) {
            return const ApiFailure(
                ApiProblem(ApiProblemKind.rejected, statusCode: 409, detail: 'home_feed_preparation_required'));
          }
          return page([card(2, age: 8)], generation: 'after-delete');
        },
        prepare: () async => const ApiSuccess(HomeFeedPreparation(ready: true, processed: 50, hasMore: false)));
    await p.start();
    await p.loadMore();
    expect(p.unsupported, false);
    expect(p.items.single.title, isEmpty);
    expect(p.items.single.preview, isEmpty);
    await tester.pump(const Duration(seconds: 1));
    await tester.pump();
    await tester.pump();
    expect(p.items.map((c) => c.id), ['conversation:2']);
    expect(p.problem, null);
    p.dispose();
  });
  testWidgets('every preparation round starts at once, with no inherited 30 s pause', (tester) async {
    var dirty = false, prepares = 0;
    final redactedAtPrepare = <bool>[];
    late final HomeFeedProvider p;
    p = HomeFeedProvider(
        owner: () => 'a',
        cache: MemoryCache(),
        fetch: ({cursor}) async => dirty
            ? const ApiFailure(
                ApiProblem(ApiProblemKind.rejected, statusCode: 409, detail: 'home_feed_preparation_required'))
            : page([card(1)]),
        prepare: () async {
          prepares++;
          redactedAtPrepare.add(p.preparing && p.items.single.title.isEmpty);
          dirty = false;
          return const ApiSuccess(HomeFeedPreparation(ready: true, processed: 1, hasMore: false));
        });
    await p.start();
    await tester.pump();
    // Each conversation write re-dirties the feed; round 4 used to wait 30 s. Writes here are 5 s apart,
    // the minimum spacing between prepare calls.
    for (var round = 1; round <= 4; round++) {
      if (round > 1) await tester.pump(const Duration(seconds: 5));
      dirty = true;
      unawaited(p.reconcileLoadedWindow());
      // 100 ms in all: the old schedule waited at least 1 s before a round's first call.
      for (var tick = 0; tick < 10; tick++) {
        await tester.pump(const Duration(milliseconds: 10));
      }
      expect(prepares, round, reason: 'round $round prepares at once');
      expect(redactedAtPrepare.last, true, reason: 'cards stay redacted until the feed is prepared');
      expect(p.preparing, false);
      expect(p.preparationStalled, false);
      expect(p.items.single.title, 'Title 1');
    }
    p.dispose();
  });
  testWidgets('preparation that keeps failing is reported as stalled', (tester) async {
    final p = HomeFeedProvider(
        owner: () => 'a',
        cache: MemoryCache(),
        fetch: ({cursor}) async => const ApiFailure(
            ApiProblem(ApiProblemKind.rejected, statusCode: 409, detail: 'home_feed_preparation_required')),
        prepare: () async => const ApiFailure(ApiProblem(ApiProblemKind.server, statusCode: 503)));
    await p.start();
    expect(p.preparationStalled, false, reason: 'a required preparation is routine at first');
    for (var i = 0; i < 20; i++) {
      await tester.pump(const Duration(seconds: 1));
    }
    expect(p.preparationStalled, true);
    p.dispose();
  });
  testWidgets('back-to-back rounds keep prepare calls 5 s apart (home:prepare allows 12 a minute)', (tester) async {
    var dirty = false, prepares = 0;
    final p = HomeFeedProvider(
        owner: () => 'a',
        cache: MemoryCache(),
        fetch: ({cursor}) async => dirty
            ? const ApiFailure(
                ApiProblem(ApiProblemKind.rejected, statusCode: 409, detail: 'home_feed_preparation_required'))
            : page([card(1)]),
        prepare: () async {
          prepares++;
          dirty = false;
          return const ApiSuccess(HomeFeedPreparation(ready: true, processed: 1, hasMore: false));
        });
    await p.start();
    await tester.pump();
    Future<void> write() async {
      dirty = true;
      unawaited(p.reconcileLoadedWindow());
      for (var tick = 0; tick < 10; tick++) {
        await tester.pump(const Duration(milliseconds: 10));
      }
    }

    await write();
    expect(prepares, 1);
    await write();
    expect(prepares, 1, reason: 'a write right after a prepare call waits out the gap');
    await tester.pump(const Duration(seconds: 5));
    await tester.pump();
    expect(prepares, 2);
    p.dispose();
  });
  testWidgets('retry restarts a stalled preparation', (tester) async {
    var failing = true, prepares = 0;
    final p = HomeFeedProvider(
        owner: () => 'a',
        cache: MemoryCache(),
        fetch: ({cursor}) async => failing
            ? const ApiFailure(
                ApiProblem(ApiProblemKind.rejected, statusCode: 409, detail: 'home_feed_preparation_required'))
            : page([card(1)]),
        prepare: () async {
          prepares++;
          return failing
              ? const ApiFailure(ApiProblem(ApiProblemKind.server, statusCode: 503))
              : const ApiSuccess(HomeFeedPreparation(ready: true, processed: 1, hasMore: false));
        });
    await p.start();
    for (var i = 0; i < 20; i++) {
      await tester.pump(const Duration(seconds: 1));
    }
    expect(p.preparationStalled, true);
    final stalledAt = prepares;
    failing = false;
    await p.retry();
    for (var i = 0; i < 6; i++) {
      await tester.pump(const Duration(seconds: 1));
    }
    expect(prepares, greaterThan(stalledAt), reason: 'retry starts a new round');
    expect(p.preparationStalled, false);
    expect(p.preparing, false);
    p.dispose();
  });
}
