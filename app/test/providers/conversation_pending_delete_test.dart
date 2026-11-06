import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/gen/siri_pigeon.g.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:omi/services/siri_integration.dart';
import 'package:omi/ui/feedback/omi_feedback.dart';

class _SiriUndoHost extends SiriIndexApi {
  List<SiriConversation> restored = [];
  Completer<void>? deleteGate;

  @override
  Future<void> upsertConversations(String uid, List<SiriConversation> rows) async {
    restored = rows;
  }

  @override
  Future<void> deleteEntities(String uid, String type, List<String> ids) async {
    await deleteGate?.future;
  }
}

/// D5: a conversation delete is held back long enough for its Undo toast to be real.
void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  late List<String> deleted;

  ConversationProvider makeProvider(List<ServerConversation> items) {
    deleted = [];
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: items, ok: true),
      isSignedIn: () => true,
    );
    provider.conversationDeleteFetcherOverride = (id) async {
      deleted.add(id);
      return true;
    };
    provider.conversations = [...items];
    provider.groupConversationsByDate();
    addTearDown(provider.dispose);
    return provider;
  }

  test('the pending window outlasts the Undo toast', () {
    expect(ConversationProvider.pendingDeleteWindow > OmiFeedbackTiming.undo, isTrue);
  });

  test('a local delete hides the row and holds the server delete back', () {
    final a = _conversation('a');
    final provider = makeProvider([a, _conversation('b')]);

    provider.deleteConversationLocally(a);

    expect(provider.conversations.map((c) => c.id), ['b']);
    expect(provider.groupedConversations.values.expand((l) => l).map((c) => c.id), ['b']);
    expect(provider.isDeletePending('a'), isTrue);
    expect(deleted, isEmpty);
  });

  test('undo restores the row and never deletes on the server', () async {
    final a = _conversation('a');
    final provider = makeProvider([a]);

    provider.deleteConversationLocally(a);
    provider.undoDeletedConversation(a);
    await Future<void>.delayed(Duration.zero);

    expect(provider.conversations.map((c) => c.id), ['a']);
    expect(provider.groupedConversations.values.expand((l) => l).map((c) => c.id), ['a']);
    expect(provider.isDeletePending('a'), isFalse);
    provider.commitPendingDelete('a');
    expect(deleted, isEmpty);
  });

  test('undo restores the conversation to Siri after the optimistic index delete', () async {
    final host = _SiriUndoHost();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'owner-a');
    addTearDown(() => SiriIntegration.testInstance = null);
    final a = _conversation('a');
    final provider = makeProvider([a]);

    provider.deleteConversationLocally(a);
    await Future<void>.delayed(Duration.zero);
    await provider.undoDeletedConversation(a);
    await SiriIntegration.current.drainIndexForTest();

    expect(host.restored.map((row) => row.id), ['a']);
  });

  test('undo completes while native delete is pending, then reindexes in order', () async {
    final host = _SiriUndoHost()..deleteGate = Completer<void>();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'owner-a');
    addTearDown(() => SiriIntegration.testInstance = null);
    final a = _conversation('a');
    final provider = makeProvider([a]);
    final deletion = provider.deleteConversationLocally(a);
    var restored = false;
    final undo = provider.undoDeletedConversation(a).then((_) => restored = true);
    await Future<void>.delayed(Duration.zero);
    expect(restored, isTrue);
    expect(host.restored, isEmpty);
    host.deleteGate!.complete();
    await deletion;
    await undo;
    await SiriIntegration.current.drainIndexForTest();
    expect(restored, isTrue);
    expect(host.restored.map((row) => row.id), ['a']);
  });

  for (final failure in ['rejected', 'throws']) {
    test('a $failure server delete restores the optimistic Siri entry', () async {
      final host = _SiriUndoHost();
      SiriIntegration.testInstance = SiriIntegration.forTest(host, 'owner-a');
      addTearDown(() => SiriIntegration.testInstance = null);
      final provider = makeProvider([_conversation('a')]);
      provider.conversationDeleteFetcherOverride = (_) async {
        if (failure == 'throws') throw StateError('offline');
        return false;
      };

      provider.deleteConversationLocally(provider.conversations.single);
      await Future<void>.delayed(Duration.zero);
      expect(host.restored, isEmpty);
      provider.commitPendingDelete('a');
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);
      await SiriIntegration.current.drainIndexForTest();

      expect(host.restored.map((row) => row.id), ['a']);
    });

    test('a $failure server delete puts the row back in the list', () async {
      final a = _conversation('a');
      final provider = makeProvider([a, _conversation('b')]);
      provider.conversationDeleteFetcherOverride = (_) async {
        if (failure == 'throws') throw StateError('offline');
        return false;
      };

      provider.deleteConversationLocally(a);
      provider.commitPendingDelete('a');
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);

      expect(provider.conversations.map((c) => c.id), unorderedEquals(['a', 'b']));
      expect(provider.displayedConversations.map((c) => c.id), unorderedEquals(['a', 'b']));
      expect(provider.memoriesToDelete, isEmpty);
    });
  }

  test('a failed server delete puts the row back in active search results', () async {
    final a = _conversation('a');
    final provider = makeProvider([]);
    provider.conversationDeleteFetcherOverride = (_) async => false;
    provider.previousQuery = 'title';
    provider.searchedConversations = [a, _conversation('b')];
    provider.groupSearchConvosByDate();

    provider.deleteConversationLocally(a);
    expect(provider.displayedConversations.map((c) => c.id), ['b']);
    provider.commitPendingDelete('a');
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);

    expect(provider.displayedConversations.map((c) => c.id), unorderedEquals(['a', 'b']));
  });

  test('a failed server delete waits for the optimistic native delete before restoring', () async {
    final host = _SiriUndoHost()..deleteGate = Completer<void>();
    SiriIntegration.testInstance = SiriIntegration.forTest(host, 'owner-a');
    addTearDown(() => SiriIntegration.testInstance = null);
    final provider = makeProvider([_conversation('a')]);
    provider.conversationDeleteFetcherOverride = (_) async => false;

    provider.deleteConversationLocally(provider.conversations.single);
    provider.commitPendingDelete('a');
    await Future<void>.delayed(Duration.zero);
    expect(host.restored, isEmpty);
    host.deleteGate!.complete();
    await SiriIntegration.current.drainIndexForTest();
    expect(host.restored.map((row) => row.id), ['a']);
  });

  test('committing sends the delete once and makes undo a no-op', () async {
    final a = _conversation('a');
    final provider = makeProvider([a]);

    provider.deleteConversationLocally(a);
    provider.commitPendingDelete('a');
    provider.commitPendingDelete('a');
    await Future<void>.delayed(Duration.zero);
    provider.undoDeletedConversation(a);

    expect(deleted, ['a']);
    expect(provider.conversations, isEmpty);
  });

  test('live upserts cannot restore a row while undo or delete is pending', () async {
    final row = _conversation('deleted');
    final keep = _conversation('keep');
    final provider = makeProvider([row, keep]);
    final response = Completer<bool>();
    provider.conversationDeleteFetcherOverride = (_) => response.future;

    await provider.deleteConversationLocally(row);
    provider.upsertConversation(row);
    expect(provider.conversations, [keep]);

    final deletion = provider.deleteConversationOnServer(row.id);
    provider.upsertConversation(row);
    expect(provider.conversations, [keep]);

    response.complete(false);
    await deletion;
    expect(provider.conversations, unorderedEquals([row, keep]));
  });

  test('confirmed deletes stay removed when an empty refresh restores cached rows', () async {
    final a = _conversation('a');
    final b = _conversation('b');
    final keep = _conversation('keep');
    await SharedPreferencesUtil().cacheConversations([a, b, keep]);
    final provider = makeProvider([a, b, keep]);

    await provider.deleteConversationLocally(a);
    await provider.deleteConversationLocally(b);
    provider.commitPendingDelete(a.id);
    provider.commitPendingDelete(b.id);
    await Future<void>.delayed(Duration.zero);

    final reopened = makeProvider([]);
    await reopened.fetchConversations();

    expect(reopened.conversations.map((row) => row.id), ['keep']);
  });

  test('a second provider cannot restore a confirmed deletion from an older page', () async {
    final a = _conversation('a');
    final keep = _conversation('keep');
    final prefs = SharedPreferencesUtil()..uid = 'fixture-owner';
    await prefs.cacheConversations([a, keep]);
    final day = makeProvider([a]);
    final pendingPage = Completer<({List<ServerConversation> items, bool ok})>();
    final home = ConversationProvider(conversationListFetcher: () => pendingPage.future, isSignedIn: () => true);
    addTearDown(home.dispose);
    home.conversations = [a, keep];
    home.groupConversationsByDate();
    final refresh = home.fetchConversations();

    await day.deleteConversationLocally(a);
    await day.deleteConversationOnServer(a.id);
    expect(home.conversations.map((row) => row.id), ['keep']);
    pendingPage.complete((items: [a, keep], ok: true));
    await refresh;
    await Future<void>.delayed(Duration.zero);

    final reopened = makeProvider([]);
    await reopened.fetchConversations();
    expect(reopened.conversations.map((row) => row.id), ['keep']);
    expect(home.conversations.map((row) => row.id), ['keep']);
    expect(home.conversationServerOffset, 1);
    expect(prefs.getStringList('cachedConversations'), [jsonEncode(keep.toJson())]);

    prefs.uid = 'other-owner';
    await prefs.cacheConversations([a, keep]);
    expect((await prefs.loadCachedConversations()).map((row) => row.id), ['a', 'keep']);
  });

  test('a load-more request retries at the cursor rebased by another provider', () async {
    final items = [for (var i = 0; i < 50; i++) _conversation('initial-$i')];
    final home = makeProvider(items);
    await home.fetchConversations();
    final page = Completer<({List<ServerConversation> items, bool ok, bool truncated})>();
    final offsets = <int>[];
    final next = _conversation('next-row');
    home.conversationPageFetcherOverride = () {
      offsets.add(home.conversationServerOffset);
      if (offsets.length == 1) return page.future;
      return Future.value((items: [next], ok: true, truncated: false));
    };
    final pagination = home.getMoreConversationsFromServer();
    final day = makeProvider([items.first]);
    await day.deleteConversationLocally(items.first);
    await day.deleteConversationOnServer(items.first.id);

    page.complete((items: [_conversation('one-too-far')], ok: true, truncated: false));
    expect(await pagination, isTrue);
    expect(offsets, [50, 49]);
    expect(home.conversations.map((row) => row.id), contains(next.id));
    expect(home.conversations.map((row) => row.id), isNot(contains('one-too-far')));
  });

  test('a confirmed delete removes matching processing cards and rejects late updates', () async {
    final row = _conversation('deleted');
    final processing = _conversation('deleted', status: ConversationStatus.processing);
    final placeholder = OptimisticProcessingPlaceholder.conversation(targetConversationId: row.id);
    final keep = _conversation('keep', status: ConversationStatus.processing);
    final day = makeProvider([row]);
    final home = makeProvider([]);
    home.addProcessingConversation(placeholder);
    home.addProcessingConversation(processing);
    home.addProcessingConversation(keep);

    await day.deleteConversationLocally(row);
    await day.deleteConversationOnServer(row.id);

    expect(home.processingConversations, [keep]);
    home.addProcessingConversation(processing);
    home.addProcessingConversation(placeholder);
    home.upsertConversation(row);
    expect(home.processingConversations, [keep]);
    expect(home.conversations, isEmpty);
  });

  test('a delete confirmed after its route closes still clears the same account cache', () async {
    final row = _conversation('deleted');
    final keep = _conversation('keep');
    final prefs = SharedPreferencesUtil()..uid = 'fixture-owner';
    await prefs.cacheConversations([row, keep]);
    final response = Completer<bool>();
    final day = ConversationProvider(isSignedIn: () => true)
      ..conversationDeleteFetcherOverride = (_) => response.future;
    final home = makeProvider([row, keep]);

    await day.deleteConversationLocally(row);
    final deletion = day.deleteConversationOnServer(row.id);
    day.dispose();
    response.complete(true);
    await deletion;

    expect(home.conversations.map((row) => row.id), ['keep']);
    expect(prefs.getStringList('cachedConversations'), [jsonEncode(keep.toJson())]);
  });

  test('a closed route cannot evict from a replacement session of the same account', () async {
    final row = _conversation('deleted');
    final prefs = SharedPreferencesUtil()..uid = 'fixture-owner';
    await prefs.cacheConversations([row]);
    final response = Completer<bool>();
    final day = ConversationProvider(isSignedIn: () => true)
      ..conversationDeleteFetcherOverride = (_) => response.future;

    await day.deleteConversationLocally(row);
    final deletion = day.deleteConversationOnServer(row.id);
    day.dispose();
    prefs.clearUserDisplayCache();
    prefs.uid = 'fixture-owner';
    await prefs.cacheConversations([row]);
    response.complete(true);
    await deletion;

    expect(prefs.getStringList('cachedConversations'), [jsonEncode(row.toJson())]);
  });

  test('a refused delete still reports failure after its route closes', () async {
    final row = _conversation('deleted');
    final response = Completer<bool>();
    final day = ConversationProvider(isSignedIn: () => true)
      ..conversationDeleteFetcherOverride = (_) => response.future;
    var failures = 0;
    await day.deleteConversationLocally(row, onFailure: () => failures++);
    final deletion = day.deleteConversationOnServer(row.id);
    day.dispose();
    response.complete(false);
    await deletion;

    expect(failures, 1);
  });

  test('a regroup during the window does not bring the row back', () {
    final a = _conversation('a');
    final provider = makeProvider([a]);

    provider.deleteConversationLocally(a);
    provider.conversations = [a];
    provider.groupConversationsByDate();

    expect(provider.groupedConversations.values.expand((l) => l), isEmpty);
  });
}

ServerConversation _conversation(String id, {ConversationStatus status = ConversationStatus.completed}) =>
    ServerConversation(
      id: id,
      createdAt: DateTime(2026, 9, 20, 10),
      structured: Structured('Title $id', 'Overview'),
      status: status,
    );
