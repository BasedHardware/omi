import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/providers/conversation_provider.dart';

import '../support/local_day.dart';

ServerConversation _convo({required String id, required DateTime startedAt}) {
  return ServerConversation(id: id, createdAt: startedAt, startedAt: startedAt, structured: Structured(id, 'overview'));
}

void main() {
  test('search grouping keeps an older top-ranked hit above a newer lower-ranked one', () {
    final olderTopHit = _convo(id: 'old-spoken', startedAt: localCalendarDay(2026, 1, 2));
    final newerLowerHit = _convo(id: 'new-overview', startedAt: localCalendarDay(2026, 8, 12));

    final grouped = groupSearchResultsPreservingRank([olderTopHit, newerLowerHit]);
    final rendered = grouped.values.expand((bucket) => bucket).map((c) => c.id).toList();

    expect(rendered, ['old-spoken', 'new-overview']);
    expect(grouped.keys.first, conversationLocalDayKey(olderTopHit.startedAt!));
  });

  test('same-day search hits stay in server rank instead of recency', () {
    // Local constructors: UTC literals at 10:00 and 18:00 split across local
    // days for UTC+7..+13 (10:00 UTC → 17:00, 18:00 UTC → 01:00 next day).
    final day = localCalendarDay(2026, 8, 12, 0);
    final first = _convo(id: 'rank-1', startedAt: day.add(const Duration(hours: 2)));
    final second = _convo(id: 'rank-2', startedAt: day.add(const Duration(hours: 8)));

    final grouped = groupSearchResultsPreservingRank([first, second]);
    expect(grouped.values.single.map((c) => c.id).toList(), ['rank-1', 'rank-2']);
  });

  test('UTC instants on one UTC day keep server rank even when they split locally', () {
    // The same UTC-day pair that used to be asserted as `.single`. Rank order
    // is the production contract; bucket count follows the host's local day.
    final first = _convo(id: 'rank-1', startedAt: DateTime.utc(2026, 8, 12, 10));
    final second = _convo(id: 'rank-2', startedAt: DateTime.utc(2026, 8, 12, 18));

    final grouped = groupSearchResultsPreservingRank([first, second]);
    final rendered = grouped.values.expand((bucket) => bucket).map((c) => c.id).toList();
    expect(rendered, ['rank-1', 'rank-2']);
    expect(
      grouped.length,
      {conversationLocalDayKey(first.startedAt!), conversationLocalDayKey(second.startedAt!)}.length,
    );
  });
}
