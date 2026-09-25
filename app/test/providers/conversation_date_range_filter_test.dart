import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';

/// Regression coverage for issue #4042: filtering the conversation list by a
/// date range instead of a single date.
///
/// `groupConversationsByDate()` is synchronous and only reprocesses the
/// already-in-memory `conversations` list, so it directly exercises the
/// client-side range predicate in `_filterOutConvos` without mocking
/// network. That predicate used to be single-day equality
/// (`convoDate != filterDate`) — converting to a range without also fixing
/// this would silently drop every result outside the *old* single day even
/// though the server-side fetch already returned the full range, which is
/// exactly the boundary bug PR #7977 hit for the sibling search-flow filter.
///
/// This does not exercise `_getDateFilterRange()` (the start/end boundary
/// normalization used for the server request) directly — it's private, and
/// injecting `conversationListFetcher` (required to keep this hermetic)
/// bypasses it entirely. Coverage here is intentionally scoped to the
/// client-side re-filter, which is the part these tests can reach.
void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  ConversationProvider makeProvider() {
    final provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
    addTearDown(provider.dispose);
    return provider;
  }

  test('a date range includes conversations on both the first and last selected day', () {
    final provider = makeProvider();
    final day1 = DateTime(2026, 7, 1, 9);
    final day2 = DateTime(2026, 7, 2, 14);
    final day3 = DateTime(2026, 7, 3, 23, 30);
    final beforeRange = DateTime(2026, 6, 30, 12);
    final afterRange = DateTime(2026, 7, 4, 0, 1);

    provider.conversations = [
      _conversation('before', beforeRange),
      _conversation('day1', day1),
      _conversation('day2', day2),
      _conversation('day3', day3),
      _conversation('after', afterRange),
    ];
    provider.selectedStartDate = DateTime(2026, 7, 1);
    provider.selectedEndDate = DateTime(2026, 7, 3);

    provider.groupConversationsByDate();

    final includedIds = provider.groupedConversations.values.expand((list) => list).map((c) => c.id).toSet();
    expect(includedIds, {'day1', 'day2', 'day3'});
    expect(includedIds.contains('before'), isFalse);
    expect(includedIds.contains('after'), isFalse);
  });

  test('no range selected shows every conversation', () {
    final provider = makeProvider();
    provider.conversations = [_conversation('a', DateTime(2026, 1, 1)), _conversation('b', DateTime(2026, 7, 1))];

    provider.groupConversationsByDate();

    final includedIds = provider.groupedConversations.values.expand((list) => list).map((c) => c.id).toSet();
    expect(includedIds, {'a', 'b'});
  });

  test('filterConversationsByDateRange sets both start and end', () async {
    final provider = makeProvider();
    final start = DateTime(2026, 7, 1);
    final end = DateTime(2026, 7, 3);

    await provider.filterConversationsByDateRange(start, end);

    expect(provider.selectedStartDate, start);
    expect(provider.selectedEndDate, end);
  });

  test('clearDateFilter nulls both start and end', () async {
    final provider = makeProvider();
    provider.selectedStartDate = DateTime(2026, 7, 1);
    provider.selectedEndDate = DateTime(2026, 7, 3);

    await provider.clearDateFilter();

    expect(provider.selectedStartDate, isNull);
    expect(provider.selectedEndDate, isNull);
  });

  test('clearUserData nulls both start and end', () {
    final provider = makeProvider();
    provider.selectedStartDate = DateTime(2026, 7, 1);
    provider.selectedEndDate = DateTime(2026, 7, 3);

    provider.clearUserData();

    expect(provider.selectedStartDate, isNull);
    expect(provider.selectedEndDate, isNull);
  });
}

ServerConversation _conversation(String id, DateTime createdAt) => ServerConversation(
      id: id,
      createdAt: createdAt,
      structured: Structured('Title', 'Overview'),
      status: ConversationStatus.completed,
    );
