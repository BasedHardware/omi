import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';

ServerConversation row(String id) => ServerConversation(
      id: id,
      createdAt: DateTime.utc(2026, 10, 1),
      structured: Structured(id, 'summary'),
      status: ConversationStatus.completed,
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('completed merge removes originals from cache, search and a reopened offline provider', () async {
    final originals = [row('a'), row('b')];
    SharedPreferencesUtil().cachedConversations = originals;
    final provider = ConversationProvider(
      conversationLifecycleFetcher: (_) async => (item: row('new-target'), ok: true),
      isSignedIn: () => true,
    )
      ..conversations = originals.toList()
      ..searchedConversations = originals.toList();
    addTearDown(provider.dispose);

    await provider.onMergeCompleted('new-target', ['a', 'b']);
    expect(provider.conversations.map((c) => c.id), ['new-target']);
    expect(provider.searchedConversations.any((c) => c.id == 'a' || c.id == 'b'), false);
    expect((await SharedPreferencesUtil().loadCachedConversations()).map((c) => c.id), ['new-target']);

    final reopened = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: false),
      isSignedIn: () => true,
    );
    addTearDown(reopened.dispose);
    await reopened.fetchConversations();
    expect(reopened.conversations.map((c) => c.id), ['new-target']);
  });

  test('a page already in flight cannot restore merged-away sources', () async {
    final page = Completer<({List<ServerConversation> items, bool ok})>();
    final provider = ConversationProvider(
      conversationListFetcher: () => page.future,
      conversationLifecycleFetcher: (_) async => (item: row('new-target'), ok: true),
      isSignedIn: () => true,
    )..conversations = [row('a'), row('b')];
    addTearDown(provider.dispose);
    final refresh = provider.fetchConversations();
    await provider.onMergeCompleted('new-target', ['a', 'b']);
    page.complete((items: [row('a'), row('b')], ok: true));
    await refresh;
    expect(provider.conversations.map((c) => c.id), ['new-target']);
  });

  test('failed target read retains original rows and merging markers', () async {
    final provider = ConversationProvider(
      conversationLifecycleFetcher: (_) async => (item: null, ok: false),
      isSignedIn: () => true,
    )
      ..conversations = [row('a'), row('b')]
      ..mergingConversationIds = {'a', 'b'};
    addTearDown(provider.dispose);
    await provider.onMergeCompleted('new-target', ['a', 'b']);
    expect(provider.conversations.map((c) => c.id), ['a', 'b']);
    expect(provider.mergingConversationIds, {'a', 'b'});
  });

  test('late completion cannot change a replacement account', () async {
    final target = Completer<({ServerConversation? item, bool ok})>();
    final provider = ConversationProvider(
      conversationLifecycleFetcher: (_) => target.future,
      isSignedIn: () => true,
    )..mergingConversationIds = {'a', 'b'};
    addTearDown(provider.dispose);
    final completion = provider.onMergeCompleted('new-target', ['a', 'b']);
    provider.clearUserData();
    provider.conversations = [row('replacement-account')];
    target.complete((item: row('new-target'), ok: true));
    await completion;
    expect(provider.conversations.map((c) => c.id), ['replacement-account']);
    expect(await SharedPreferencesUtil().loadCachedConversations(), isEmpty);
  });
}
