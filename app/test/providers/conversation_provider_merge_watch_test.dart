import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/conversation_merge_watch.dart';

ServerConversation row(String id, {ConversationStatus status = ConversationStatus.completed}) => ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026, 10, 1),
      structured: Structured(id, 'summary'),
      status: status,
    );
const missing = ApiFailure<ServerConversation>(ApiProblem(ApiProblemKind.notFound, statusCode: 404));

void main() {
  for (final kind in [
    ApiProblemKind.transport,
    ApiProblemKind.paymentRequired,
    ApiProblemKind.forbidden,
    ApiProblemKind.unprocessable,
    ApiProblemKind.server,
    ApiProblemKind.decode
  ]) {
    test('$kind is not evidence that a source was deleted', () {
      fakeAsync((clock) {
        final server = <String, ApiResult<ServerConversation>>{
          'a': ApiFailure(ApiProblem(kind)),
          'b': missing,
          'target': ApiSuccess(row('target'))
        };
        var completed = false;
        final watch = ConversationMergeWatch(
            sourceIds: ['a', 'b'],
            targetId: 'target',
            fetch: (id) async => server[id]!,
            isCurrent: () => true,
            onCompleted: (_) async {
              completed = true;
            },
            onRefresh: (_) async {},
            interval: const Duration(seconds: 1),
            limit: const Duration(minutes: 3));
        clock.elapse(const Duration(seconds: 2));
        expect(completed, false);
        server['a'] = missing;
        clock.elapse(const Duration(seconds: 1));
        expect(completed, true);
        watch.cancel();
      });
    });
  }

  test('a completed original is never mistaken for the new merged target', () {
    fakeAsync((clock) {
      final server = <String, ApiResult<ServerConversation>>{
        'a': ApiSuccess(row('a')),
        'b': missing,
        'target': ApiSuccess(row('target'))
      };
      final completed = <String>[];
      final watch = ConversationMergeWatch(
          sourceIds: ['a', 'b'],
          targetId: 'target',
          fetch: (id) async => server[id]!,
          isCurrent: () => true,
          onCompleted: (target) async {
            completed.add(target.id);
          },
          onRefresh: (_) async {},
          interval: const Duration(seconds: 1),
          limit: const Duration(minutes: 3));
      clock.elapse(const Duration(seconds: 1));
      expect(completed, isEmpty);
      server['a'] = missing;
      server['target'] = ApiSuccess(row('target', status: ConversationStatus.processing));
      clock.elapse(const Duration(seconds: 1));
      expect(completed, isEmpty);
      server['target'] = ApiSuccess(row('target'));
      clock.elapse(const Duration(seconds: 1));
      expect(completed, ['target']);
      watch.cancel();
    });
  });

  test('old server without target ID refreshes only after every source returns 404', () {
    fakeAsync((clock) {
      final refreshes = <bool>[];
      final watch = ConversationMergeWatch(
          sourceIds: ['a', 'b'],
          targetId: null,
          fetch: (_) async => missing,
          isCurrent: () => true,
          onCompleted: (_) async => fail('no target'),
          onRefresh: (gone) async {
            refreshes.add(gone);
          },
          interval: const Duration(seconds: 1),
          limit: const Duration(minutes: 3));
      clock.elapse(const Duration(seconds: 5));
      expect(refreshes, [true]);
      watch.cancel();
    });
  });

  test('deadline cancels probes and requests a nonterminal refresh once', () {
    fakeAsync((clock) {
      final refreshes = <bool>[];
      var reads = 0;
      final watch = ConversationMergeWatch(
          sourceIds: ['a', 'b'],
          targetId: 'target',
          fetch: (id) async {
            reads++;
            return ApiSuccess(row(id));
          },
          isCurrent: () => true,
          onCompleted: (_) async => fail('unfinished'),
          onRefresh: (gone) async {
            refreshes.add(gone);
          },
          interval: const Duration(seconds: 1),
          limit: const Duration(seconds: 3));
      clock.elapse(const Duration(seconds: 4));
      final stoppedAt = reads;
      clock.elapse(const Duration(minutes: 2));
      expect(reads, stoppedAt);
      expect(refreshes, [false]);
      watch.cancel();
    });
  });

  test('a slow server cleanup remains observed after the fast polling window without push', () {
    fakeAsync((clock) {
      var done = false;
      var completed = false;
      var recoveryRefreshes = 0;
      var reads = 0;
      final watch = ConversationMergeWatch(
          sourceIds: ['a', 'b'],
          targetId: 'target',
          fetch: (id) async {
            reads++;
            return id == 'target'
                ? ApiSuccess(row('target'))
                : done
                    ? missing
                    : ApiSuccess(row(id, status: ConversationStatus.merging));
          },
          isCurrent: () => true,
          onCompleted: (_) async {
            completed = true;
          },
          onRefresh: (_) async => fail('must keep observing the admitted operation'),
          onRecoveryRefresh: () async {
            recoveryRefreshes++;
          },
          interval: const Duration(seconds: 1),
          limit: const Duration(seconds: 3),
          recoveryInterval: const Duration(seconds: 10),
          recoveryLimit: const Duration(minutes: 1));
      clock.elapse(const Duration(seconds: 4));
      expect(completed, false);
      expect(recoveryRefreshes, 1);
      final fastReads = reads;
      clock.elapse(const Duration(seconds: 5));
      expect(reads, fastReads, reason: 'recovery probes use the lower bounded rate');
      done = true;
      clock.elapse(const Duration(seconds: 10));
      expect(completed, true);
      watch.cancel();
    });
  });

  test('unreadable target never announces success but deadline retains proven source absence', () {
    fakeAsync((clock) {
      final refreshes = <bool>[];
      final watch = ConversationMergeWatch(
          sourceIds: ['a', 'b'],
          targetId: 'target',
          fetch: (id) async => id == 'target'
              ? const ApiFailure<ServerConversation>(ApiProblem(ApiProblemKind.paymentRequired))
              : missing,
          isCurrent: () => true,
          onCompleted: (_) async => fail('locked target cannot complete'),
          onRefresh: (gone) async {
            refreshes.add(gone);
          },
          interval: const Duration(seconds: 1),
          limit: const Duration(seconds: 3));
      clock.elapse(const Duration(seconds: 5));
      expect(refreshes, [true]);
      watch.cancel();
    });
  });

  test('deadline refresh failure is contained and cannot escape as an unhandled timer error', () {
    fakeAsync((clock) {
      final watch = ConversationMergeWatch(
          sourceIds: ['a', 'b'],
          targetId: 'target',
          fetch: (id) async => ApiSuccess(row(id)),
          isCurrent: () => true,
          onCompleted: (_) async => fail('unfinished'),
          onRefresh: (_) async => throw StateError('synthetic cache unavailable'),
          interval: const Duration(seconds: 1),
          limit: const Duration(seconds: 3));
      clock.elapse(const Duration(seconds: 5));
      watch.cancel();
    });
  });

  test('an account/backend fence suppresses a late in-flight read', () {
    fakeAsync((clock) {
      final result = Completer<ApiResult<ServerConversation>>();
      var current = true;
      final watch = ConversationMergeWatch(
          sourceIds: ['a', 'b'],
          targetId: 'target',
          fetch: (_) => result.future,
          isCurrent: () => current,
          onCompleted: (_) async => fail('stale completion'),
          onRefresh: (_) async => fail('stale refresh'),
          interval: const Duration(seconds: 1),
          limit: const Duration(seconds: 3));
      clock.elapse(const Duration(seconds: 1));
      current = false;
      result.complete(missing);
      clock.elapse(const Duration(seconds: 5));
      watch.cancel();
    });
  });

  test('older admission response without target ID remains decodable', () {
    final response = MergeConversationsResponse.fromJson({
      'status': 'merging',
      'message': 'Merge started',
      'conversation_ids': ['a', 'b'],
    });
    expect(response.mergedConversationId, isNull);
    expect(response.conversationIds, ['a', 'b']);
  });

  group('persisted provider watch', () {
    setUp(() async {
      Env.overrideApiBaseUrl('http://127.0.0.1:1/');
      SharedPreferences.setMockInitialValues({'uid': 'merge-owner'});
      await SharedPreferencesUtil.init();
    });
    tearDown(Env.clearApiBaseUrlOverrideForTesting);

    test('reopen resumes the same new target without push and removes originals from cache', () async {
      var done = false;
      ApiResult<ServerConversation> fetch(String id) => done && id != 'target' ? missing : ApiSuccess(row(id));
      ConversationProvider make() => ConversationProvider(
            mergeConversationFetcher: (id) async => fetch(id),
            isSignedIn: () => true,
            conversationListFetcher: () async => (items: [row('a'), row('b')], ok: true),
          )..mergeProbeInterval = const Duration(milliseconds: 5);
      final before = make();
      before.watchMerge(['a', 'b'], targetId: 'target');
      before.dispose();
      final reopened = make();
      addTearDown(reopened.dispose);
      final completion = Completer<void>();
      reopened.addListener(() {
        if (!completion.isCompleted && reopened.conversations.any((c) => c.id == 'target')) completion.complete();
      });
      await reopened.fetchConversations();
      done = true;
      await completion.future.timeout(const Duration(seconds: 5));
      expect(reopened.conversations.map((c) => c.id), ['target']);
      expect((await SharedPreferencesUtil().loadCachedConversations()).map((c) => c.id), ['target']);
      expect(SharedPreferencesUtil().getString('pendingConversationMerges:merge-owner'), contains('[]'));
    });

    test('old backend source 404s remove stale cache even when its list is empty', () async {
      SharedPreferencesUtil().cachedConversations = [row('a'), row('b')];
      final provider = ConversationProvider(
        isSignedIn: () => true,
        mergeConversationFetcher: (_) async => missing,
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      )
        ..mergeProbeInterval = const Duration(milliseconds: 5)
        ..conversations = [row('a'), row('b')];
      addTearDown(provider.dispose);
      final settled = Completer<void>();
      provider.addListener(() {
        if (!settled.isCompleted && provider.conversations.isEmpty) settled.complete();
      });
      provider.watchMerge(['a', 'b']);
      await settled.future.timeout(const Duration(seconds: 5));
      expect(await SharedPreferencesUtil().loadCachedConversations(), isEmpty);
      final reopened = ConversationProvider(
          isSignedIn: () => true, conversationListFetcher: () async => (items: <ServerConversation>[], ok: false));
      addTearDown(reopened.dispose);
      await reopened.fetchConversations();
      expect(reopened.conversations, isEmpty);
    });

    test('old backend cleanup preserves unrelated cached rows pending deletion for undo', () async {
      SharedPreferencesUtil().cachedConversations = [row('a'), row('b'), row('unrelated-undo')];
      final provider = ConversationProvider(
        isSignedIn: () => true,
        mergeConversationFetcher: (_) async => missing,
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      )
        ..mergeProbeInterval = const Duration(milliseconds: 5)
        ..conversations = [row('a'), row('b')]
        ..memoriesToDelete = {'unrelated-undo': row('unrelated-undo')};
      addTearDown(provider.dispose);
      final settled = Completer<void>();
      provider.addListener(() {
        if (!settled.isCompleted && provider.conversations.isEmpty) settled.complete();
      });
      provider.watchMerge(['a', 'b']);
      await settled.future.timeout(const Duration(seconds: 5));
      expect((await SharedPreferencesUtil().loadCachedConversations()).map((c) => c.id), ['unrelated-undo']);
    });

    test('another backend does not restore this backend journal', () async {
      final before = ConversationProvider(isSignedIn: () => true);
      before.watchMerge(['a', 'b'], targetId: 'target');
      before.dispose();
      Env.overrideApiBaseUrl('http://127.0.0.1:2/');
      var reads = 0;
      final reopened = ConversationProvider(
          isSignedIn: () => true,
          mergeConversationFetcher: (_) async {
            reads++;
            return missing;
          },
          conversationListFetcher: () async => (items: <ServerConversation>[], ok: true));
      addTearDown(reopened.dispose);
      await reopened.fetchConversations();
      expect(reopened.mergingConversationIds, isEmpty);
      expect(reads, 0);
    });
  });
}
