part of 'conversation_provider.dart';

/// Home fetch projection keeps its held replacements and storage cursor in one boundary.
extension _ConversationHomeFetch on ConversationProvider {
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
