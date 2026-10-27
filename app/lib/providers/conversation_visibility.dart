part of 'conversation_provider.dart';

/// Visibility is reconciled across canonical, search and grouped projections.
extension _ConversationVisibility on ConversationProvider {
  bool _matchesActiveConversationFilters(ServerConversation conversation) {
    if (conversation.deleted || conversation.isMergedDonor || (!showDiscardedConversations && conversation.discarded)) {
      return false;
    }
    if (showStarredOnly && !conversation.starred) return false;
    if (selectedStartDate != null && selectedEndDate != null) {
      final conversationDate = conversationLocalDayKey(conversation.startedAt ?? conversation.createdAt);
      final startDay = DateTime(selectedStartDate!.year, selectedStartDate!.month, selectedStartDate!.day);
      final endDay = DateTime(selectedEndDate!.year, selectedEndDate!.month, selectedEndDate!.day);
      if (conversationDate.isBefore(startDay) || conversationDate.isAfter(endDay)) return false;
    }
    if (selectedFolderId != null && conversation.folderId != selectedFolderId) return false;
    return true;
  }

  void _updateConversationProjections(ServerConversation conversation) {
    if (conversation.isMergedDonor) _mergedAwayConversationIds.add(conversation.id);
    if (conversation.deleted || conversation.isMergedDonor) {
      conversations.removeWhere((row) => row.id == conversation.id);
      searchedConversations.removeWhere((row) => row.id == conversation.id);
      processingConversations.removeWhere((row) => row.id == conversation.id);
    }
    final canonicalIndex = conversations.indexWhere((element) => element.id == conversation.id);
    if (canonicalIndex != -1) {
      conversations[canonicalIndex] = conversation;
    }
    final searchedIndex = searchedConversations.indexWhere((element) => element.id == conversation.id);
    if (searchedIndex != -1) {
      searchedConversations[searchedIndex] = conversation;
    }
    if (conversation.deleted || conversation.isMergedDonor || (conversation.discarded && !showDiscardedConversations)) {
      if (hasActiveSearch) {
        _groupSearchConvosByDateWithoutNotify();
      } else {
        _groupConversationsByDateWithoutNotify();
      }
    } else {
      for (final group in groupedConversations.values) {
        final groupedIndex = group.indexWhere((element) => element.id == conversation.id);
        if (groupedIndex != -1) group[groupedIndex] = conversation;
      }
    }
    SiriIntegration.current.queueUpsertConversations([conversation]);
    notifyListeners();
  }
}
