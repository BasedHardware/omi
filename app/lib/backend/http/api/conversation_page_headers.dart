// The list pagination headers of GET /v1/conversations: one parse, one end-of-list rule.

/// Pagination facts `GET /v1/conversations` sends in headers, so the list body keeps its shape.
///
/// [hasMore] is the server's own end-of-list answer: a page cut short by a run of hidden rows still
/// has more behind it, so a short page is not the end. [nextCursor] resumes after the last row read;
/// it is present only where the server's cursor is enabled. Both are null from an older server.
class ConversationPageHeaders {
  const ConversationPageHeaders({this.hasMore, this.nextCursor, this.homeMode, this.dayCursorEnabled = false});

  final bool? hasMore;
  final String? nextCursor;
  final String? homeMode;
  final bool dayCursorEnabled;

  static const homeModeHeader = 'X-Omi-Home-Page-Mode';

  static ConversationPageHeaders parse(Map<String, String> headers) {
    final more = headers['x-omi-has-more'];
    final cursor = headers['x-omi-next-cursor'];
    final mode = headers[homeModeHeader.toLowerCase()];
    return ConversationPageHeaders(
      homeMode: mode == 'indexed' || mode == 'legacy' ? mode : null,
      hasMore: more == 'true' ? true : (more == 'false' ? false : null),
      nextCursor: cursor == null || cursor.isEmpty ? null : cursor,
      dayCursorEnabled: headers['x-omi-day-cursor'] == '1',
    );
  }

  /// Whether to request another page: the server's answer when it sent one, else a full page that
  /// was not cut short by the read budget. The server's answer covers a budget cut too: it says more
  /// only when the cut page advanced, so the next request resumes past it rather than repeating it.
  bool more({required int storageCount, required int pageSize, required bool truncated}) =>
      hasMore ?? (!truncated && storageCount >= pageSize);
}
