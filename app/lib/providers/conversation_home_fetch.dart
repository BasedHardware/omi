part of 'conversation_provider.dart';

/// One Home list page as the provider consumes it: rows, the storage-row offset advance, and the
/// server's pagination headers ([ConversationPageHeaders]; empty from an older server).
typedef _HomePage = ({
  List<ServerConversation> items,
  bool ok,
  bool truncated,
  int storageCount,
  ConversationPageHeaders page,
  ApiResult<List<ServerConversation>>? typed
});

/// Home fetch projection keeps its held replacements and storage cursor in one boundary.
extension _ConversationHomeFetch on ConversationProvider {
  int _recordServerPageIds(List<ServerConversation> rows, int storageCount) {
    final prefs = SharedPreferencesUtil();
    var retained = storageCount;
    for (final row in rows) {
      if (prefs.isConversationDeleteConfirmed(row.id)) {
        // This response still counted a row that is gone from the next page's storage cursor.
        retained--;
      } else {
        _conversationServerLoadedIds.add(row.id);
      }
    }
    return retained < 0 ? 0 : retained;
  }

  /// A newest-page refresh proves nothing about cached pages older than its boundary.
  Iterable<ServerConversation> _cachedRowsBeforePage(
      List<ServerConversation> page, Iterable<ServerConversation> cached) sync* {
    if (page.isEmpty) return;
    // GET /v1/conversations orders storage pages by created_at, not recorded start.
    final boundary = page.map((c) => c.createdAt).reduce((a, b) => a.isBefore(b) ? a : b);
    for (final row in _filterPendingDeletes(cached.toList())) {
      if (_isHomeListRow(row) && !row.createdAt.isAfter(boundary) && _matchesActiveConversationFilters(row)) {
        yield row;
      }
    }
  }

  Future<bool> _restoreCacheForFetch(int generation, int fetchRevision) async {
    final ownerUid = SharedPreferencesUtil().uid;
    final cached = await _conversationCacheLoader();
    if (generation != _sessionGeneration ||
        fetchRevision != _conversationFetchRevision ||
        !_isSignedIn() ||
        SharedPreferencesUtil().uid != ownerUid) {
      return false;
    }
    final activeProcessingIds = processingConversations
        .where((conversation) => _isActiveProcessingStatus(conversation.status))
        .map((conversation) => conversation.id)
        .toSet();
    bool visible(ServerConversation conversation) =>
        !activeProcessingIds.contains(conversation.id) &&
        !_isHiddenByDelete(conversation.id) &&
        _matchesActiveConversationFilters(conversation);
    // The fallback starts with an empty list. Rows delivered during decode
    // (including local phone rows) win over older cached objects with that ID.
    final restored = <String, ServerConversation>{
      for (final conversation in cached)
        if (visible(conversation)) conversation.id: conversation,
      for (final conversation in conversations)
        if (visible(conversation)) conversation.id: conversation,
      for (final conversation in _phoneOnlyConversations.values)
        if (visible(conversation)) conversation.id: conversation,
    };
    conversations = restored.values.map(_restoreHomeProcessingProjection).toList()
      ..sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));
    return true;
  }

  Map<String, List<ServerConversation>> get _homeEpisodeAcknowledgements => !hasActiveSearch &&
          selectedFolderId == null &&
          !showStarredOnly &&
          !showDiscardedConversations &&
          selectedStartDate == null &&
          !showShortConversations &&
          !isSelectionModeActive
      ? acknowledgeLoadedHomeMembers(heldHomeEpisodes?.call() ?? const {}, conversations)
      : const {};
  _HomePage _packTypedConversationList(ApiResult<List<ServerConversation>> typed,
      {int? storageCount, ConversationPageHeaders page = const ConversationPageHeaders()}) {
    return switch (typed) {
      ApiSuccess(:final data, :final truncated) => (
          items: data,
          ok: true,
          truncated: truncated,
          storageCount: storageCount ?? data.length,
          page: page,
          typed: typed
        ),
      ApiFailure() => (
          items: <ServerConversation>[],
          ok: false,
          truncated: false,
          storageCount: 0,
          page: const ConversationPageHeaders(),
          typed: typed
        ),
    };
  }

  /// [since] bounds the read to rows created at or after it (the recent-rows refresh); the
  /// default reads the newest page.
  Future<_HomePage> _getConversationsFromServer({DateTime? since}) async {
    final typedApi = _conversationApi;
    var page = const ConversationPageHeaders();
    if (typedApi != null) {
      var (startDate, endDate) = _getDateFilterRange();
      startDate = since ?? startDate;
      var storageCount = 0;
      final typed = await typedApi.list(
        heldHomeEpisodes: _homeEpisodeAcknowledgements,
        onStorageCount: (count) => storageCount = count,
        onPageHeaders: (headers) => page = headers,
        includeDiscarded: showDiscardedConversations,
        startDate: startDate,
        endDate: endDate,
        folderId: selectedFolderId,
        starred: showStarredOnly ? true : null,
      );
      return _packTypedConversationList(typed, storageCount: storageCount, page: page);
    }
    final fetcher = _conversationListFetcher;
    if (fetcher != null) {
      final result = await fetcher();
      return (
        items: result.items,
        ok: result.ok,
        truncated: false,
        storageCount: result.items.length,
        page: page,
        typed: null
      );
    }

    var (startDate, endDate) = _getDateFilterRange();
    startDate = since ?? startDate;

    var storageCount = 0;
    final result = await getConversationsResult(
      heldHomeEpisodes: _homeEpisodeAcknowledgements,
      onStorageCount: (count) => storageCount = count,
      onPageHeaders: (headers) => page = headers,
      includeDiscarded: showDiscardedConversations,
      startDate: startDate,
      endDate: endDate,
      folderId: selectedFolderId,
      starred: showStarredOnly ? true : null,
    );
    return (
      items: result.items,
      ok: result.ok,
      truncated: result.truncated,
      storageCount: storageCount,
      page: page,
      typed: null
    );
  }

  Future<_HomePage> _getTypedHomePage(
      ConversationApi api, int offset, String? cursor, DateTime? startDate, DateTime? endDate) async {
    var storageCount = 0;
    var page = const ConversationPageHeaders();
    final result = await api.list(
      heldHomeEpisodes: _homeEpisodeAcknowledgements,
      onStorageCount: (count) => storageCount = count,
      onPageHeaders: (headers) => page = headers,
      limit: ConversationProvider._conversationPageSize,
      offset: offset,
      cursor: cursor,
      includeDiscarded: showDiscardedConversations,
      startDate: startDate,
      endDate: endDate,
      folderId: selectedFolderId,
      starred: showStarredOnly ? true : null,
    );
    return _packTypedConversationList(result, storageCount: storageCount, page: page);
  }
}
