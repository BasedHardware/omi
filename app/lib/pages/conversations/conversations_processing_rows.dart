part of 'conversations_page.dart';

/// Recording blocks sort by time too; pin the already-folded processing row
/// before them. Live capture is inserted immediately before it afterwards.
List<_ConversationListRow> _processingFirst(List<_ConversationListRow> rows, Set<String> processingIds,
    {bool enabled = true}) {
  if (!enabled) return rows;
  final pending = <DateTime, List<_ConversationListRow>>{};
  for (final row in rows) {
    if (row.kind == _ConversationListRowKind.conversation && processingIds.contains(row.conversation?.id)) {
      (pending[row.date] ??= []).add(row);
    }
  }
  return [
    for (final row in rows)
      if (row.kind != _ConversationListRowKind.conversation || !processingIds.contains(row.conversation?.id)) ...[
        row,
        if (row.kind == _ConversationListRowKind.dateHeader) ...?pending[row.date],
      ],
  ];
}

List<_ConversationListRow> _withTodayRow(List<_ConversationListRow> rows, DateTime now, _ConversationListRowKind kind) {
  if (rows.isEmpty) return rows;
  final today = DateTime(now.year, now.month, now.day);
  final header = rows.indexWhere((r) => r.kind == _ConversationListRowKind.dateHeader && r.date == today);
  _ConversationListRow todayRow(_ConversationListRowKind kind, {bool isFirst = false}) =>
      (kind: kind, date: today, isFirst: isFirst, conversation: null, recording: null, conversationIndex: -1);
  if (header >= 0) {
    var at = header + 1;
    while (at < rows.length &&
        (rows[at].kind == _ConversationListRowKind.liveEpisode ||
            rows[at].kind == _ConversationListRowKind.v3LivePlaceholder)) {
      at++;
    }
    return [...rows.take(at), todayRow(kind), ...rows.skip(at)];
  }
  final opened = rows.indexWhere((r) => r.kind == kind);
  if (opened >= 0) return rows;
  // A row that already opened Today (the live episode) carries the header; sit right under it.
  final todayOpener = rows.indexWhere(
    (r) => r.date == today && r.isFirst && r.kind != _ConversationListRowKind.topSpacer,
  );
  if (todayOpener >= 0) {
    return [...rows.take(todayOpener + 1), todayRow(kind), ...rows.skip(todayOpener + 1)];
  }
  // rows.first is the list's top spacer.
  return [
    rows.first,
    todayRow(kind, isFirst: true),
    todayRow(_ConversationListRowKind.groupSpacer),
    for (final r in rows.skip(1))
      r.kind == _ConversationListRowKind.dateHeader && r.isFirst
          ? (kind: r.kind, date: r.date, isFirst: false, conversation: null, recording: null, conversationIndex: -1)
          : r,
  ];
}

/// One row per conversation still processing, right under Today's live row: the conversation the
/// person just ended (Wrap up, a pendant double-tap) shows at once, then turns into its own row.
List<_ConversationListRow> _withProcessingRows(
  List<_ConversationListRow> rows,
  List<ServerConversation> processing,
  DateTime now,
) {
  if (processing.isEmpty) return rows;
  // A pending-only Home still needs a Today slot; the ordinary list builder
  // returns no spacer when there are no completed conversations yet.
  final base = rows.isEmpty
      ? <_ConversationListRow>[
          (
            kind: _ConversationListRowKind.topSpacer,
            date: DateUtils.dateOnly(now),
            isFirst: false,
            conversation: null,
            recording: null,
            conversationIndex: -1,
          ),
        ]
      : rows;
  final marked = _withTodayRow(base, now, _ConversationListRowKind.processing);
  final at = marked.indexWhere((r) => r.kind == _ConversationListRowKind.processing);
  if (at < 0) return rows;
  final slot = marked[at];
  return [
    ...marked.take(at),
    for (var i = 0; i < processing.length; i++)
      (
        kind: _ConversationListRowKind.processing,
        date: slot.date,
        isFirst: slot.isFirst && i == 0,
        conversation: processing[i],
        recording: null,
        conversationIndex: -1,
      ),
    ...marked.skip(at + 1),
  ];
}
