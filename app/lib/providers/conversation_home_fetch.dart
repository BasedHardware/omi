part of 'conversation_provider.dart';

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
      if (row.status == ConversationStatus.completed &&
          !row.createdAt.isAfter(boundary) &&
          _matchesActiveConversationFilters(row)) {
        yield row;
      }
    }
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
  ({
    List<ServerConversation> items,
    bool ok,
    bool truncated,
    int storageCount,
    ApiResult<List<ServerConversation>>? typed
  }) _packTypedConversationList(ApiResult<List<ServerConversation>> typed, {int? storageCount}) {
    return switch (typed) {
      ApiSuccess(:final data, :final truncated) => (
          items: data,
          ok: true,
          truncated: truncated,
          storageCount: storageCount ?? data.length,
          typed: typed
        ),
      ApiFailure() => (items: <ServerConversation>[], ok: false, truncated: false, storageCount: 0, typed: typed),
    };
  }

  Future<
      ({
        List<ServerConversation> items,
        bool ok,
        bool truncated,
        int storageCount,
        ApiResult<List<ServerConversation>>? typed
      })> _getConversationsFromServer() async {
    final typedApi = _conversationApi;
    if (typedApi != null) {
      final (startDate, endDate) = _getDateFilterRange();
      var storageCount = 0;
      final typed = await typedApi.list(
        heldHomeEpisodes: _homeEpisodeAcknowledgements,
        onStorageCount: (count) => storageCount = count,
        includeDiscarded: showDiscardedConversations,
        startDate: startDate,
        endDate: endDate,
        folderId: selectedFolderId,
        starred: showStarredOnly ? true : null,
      );
      return _packTypedConversationList(typed, storageCount: storageCount);
    }
    final fetcher = _conversationListFetcher;
    if (fetcher != null) {
      final result = await fetcher();
      return (items: result.items, ok: result.ok, truncated: false, storageCount: result.items.length, typed: null);
    }

    final (startDate, endDate) = _getDateFilterRange();

    var storageCount = 0;
    final result = await getConversationsResult(
      heldHomeEpisodes: _homeEpisodeAcknowledgements,
      onStorageCount: (count) => storageCount = count,
      includeDiscarded: showDiscardedConversations,
      startDate: startDate,
      endDate: endDate,
      folderId: selectedFolderId,
      starred: showStarredOnly ? true : null,
    );
    return (items: result.items, ok: result.ok, truncated: result.truncated, storageCount: storageCount, typed: null);
  }

  Future<
      ({
        List<ServerConversation> items,
        bool ok,
        bool truncated,
        int storageCount,
        ApiResult<List<ServerConversation>>? typed
      })> _getTypedHomePage(ConversationApi api, int offset, DateTime? startDate, DateTime? endDate) async {
    var storageCount = 0;
    final result = await api.list(
      heldHomeEpisodes: _homeEpisodeAcknowledgements,
      onStorageCount: (count) => storageCount = count,
      limit: ConversationProvider._conversationPageSize,
      offset: offset,
      includeDiscarded: showDiscardedConversations,
      startDate: startDate,
      endDate: endDate,
      folderId: selectedFolderId,
      starred: showStarredOnly ? true : null,
    );
    return _packTypedConversationList(result, storageCount: storageCount);
  }
}
