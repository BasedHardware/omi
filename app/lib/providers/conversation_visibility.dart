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
    _publishConversationChange();
  }

  void _replaceBridgedProjections(String donorId, ServerConversation survivor) {
    _mergedAwayConversationIds.add(donorId);
    final completed = survivor.status == ConversationStatus.completed && !survivor.deleted && !survivor.isMergedDonor;
    conversations
        .removeWhere((conversation) => conversation.id == donorId || (!completed && conversation.id == survivor.id));
    final survivorIndex = conversations.indexWhere((conversation) => conversation.id == survivor.id);
    if (completed) {
      if (survivorIndex == -1) {
        conversations.add(survivor);
      } else {
        conversations[survivorIndex] = survivor;
      }
    }
    conversations.sort((a, b) => (b.startedAt ?? b.createdAt).compareTo(a.startedAt ?? a.createdAt));

    final searchedDonorIndex = searchedConversations.indexWhere((conversation) => conversation.id == donorId);
    searchedConversations
        .removeWhere((conversation) => conversation.id == donorId || (!completed && conversation.id == survivor.id));
    final searchedSurvivorIndex = searchedConversations.indexWhere((conversation) => conversation.id == survivor.id);
    if (completed && searchedSurvivorIndex != -1) {
      searchedConversations[searchedSurvivorIndex] = survivor;
    } else if (completed && searchedDonorIndex != -1) {
      searchedConversations.insert(searchedDonorIndex.clamp(0, searchedConversations.length), survivor);
    }
    if (hasActiveSearch) {
      _groupSearchConvosByDateWithoutNotify();
    } else {
      _groupConversationsByDateWithoutNotify();
    }
    _publishConversationChange();
  }
}
