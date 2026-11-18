// The list pagination headers of GET /v1/conversations: one parse, one end-of-list rule.

/// Pagination facts `GET /v1/conversations` sends in headers, so the list body keeps its shape.
///
/// [hasMore] is the server's own end-of-list answer: a page cut short by a run of hidden rows still
/// has more behind it, so a short page is not the end. [nextCursor] resumes after the last row read;
/// it is present only where the server's cursor is enabled. Both are null from an older server.
class ConversationPageHeaders {
  const ConversationPageHeaders({this.hasMore, this.nextCursor});

  final bool? hasMore;
  final String? nextCursor;

  static ConversationPageHeaders parse(Map<String, String> headers) {
    final more = headers['x-omi-has-more'];
    final cursor = headers['x-omi-next-cursor'];
    return ConversationPageHeaders(
      hasMore: more == 'true' ? true : (more == 'false' ? false : null),
      nextCursor: cursor == null || cursor.isEmpty ? null : cursor,
    );
  }

  /// Whether to request another page: the server's answer when it sent one, else a full page.
  bool more({required int storageCount, required int pageSize, required bool truncated}) =>
      !truncated && (hasMore ?? storageCount >= pageSize);
}
