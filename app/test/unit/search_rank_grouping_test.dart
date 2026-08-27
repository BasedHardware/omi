import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';

ServerConversation _convo({required String id, required DateTime startedAt}) {
  return ServerConversation(
    id: id,
    createdAt: startedAt,
    startedAt: startedAt,
    structured: Structured(id, 'overview'),
  );
}

void main() {
  test('search grouping keeps an older top-ranked hit above a newer lower-ranked one', () {
    final olderTopHit = _convo(id: 'old-spoken', startedAt: DateTime.utc(2026, 1, 2, 12));
    final newerLowerHit = _convo(id: 'new-overview', startedAt: DateTime.utc(2026, 8, 12, 12));

    final grouped = groupSearchResultsPreservingRank([olderTopHit, newerLowerHit]);
    final rendered = grouped.values.expand((bucket) => bucket).map((c) => c.id).toList();

    expect(rendered, ['old-spoken', 'new-overview']);
    expect(grouped.keys.first, conversationLocalDayKey(olderTopHit.startedAt!));
  });

  test('same-day search hits stay in server rank instead of recency', () {
    final day = DateTime.utc(2026, 8, 12, 10);
    final first = _convo(id: 'rank-1', startedAt: day.add(const Duration(hours: 2)));
    final second = _convo(id: 'rank-2', startedAt: day.add(const Duration(hours: 8)));

    final grouped = groupSearchResultsPreservingRank([first, second]);
    expect(grouped.values.single.map((c) => c.id).toList(), ['rank-1', 'rank-2']);
  });
}
