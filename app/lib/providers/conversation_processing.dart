part of 'conversation_provider.dart';

/// Reconcile pending Home rows through the provider's existing page/detail owner.
extension _ConversationProcessingLifecycle on ConversationProvider {
  void _cancelProcessingPlaceholderTimers() {
    _processingPlaceholderTimeout?.cancel();
    _processingPlaceholderTimeout = null;
  }

  void _syncProcessingReconcileTimer() {
    if (processingConversations.isEmpty) {
      _processingReconcileTimer?.cancel();
      _processingReconcileTimer = null;
      return;
    }
    _processingReconcileTimer ??= Timer.periodic(const Duration(seconds: 15), (_) {
      unawaited(_refreshProcessingRows());
    });
  }

  Future<void> _refreshProcessingRows() async {
    _syncProcessingReconcileTimer();
    if (processingConversations.isEmpty) return;
    await _refreshProcessingLifecycle();
  }

  Future<void> _refreshProcessingLifecycle() async {
    if (!_isSignedIn() || isLoadingConversations) return;
    final state = WidgetsBinding.instance.lifecycleState;
    if (state != null && state != AppLifecycleState.resumed) return;
    try {
      await forceRefreshConversations();
    } catch (error) {
      Logger.debug('Processing lifecycle refresh failed: ${error.runtimeType}');
    }
  }

  bool _isActiveProcessingStatus(ConversationStatus status) {
    return status == ConversationStatus.processing || status == ConversationStatus.merging;
  }

  Map<String, ServerConversation> _realProcessingConversationsById() => {
        for (final conversation in processingConversations.whereType<OptimisticProcessingConversation>())
          if (conversation.targetConversationId != null && conversation.targetConversationId != '0')
            conversation.targetConversationId!: conversation,
        for (final conversation in processingConversations)
          if (conversation.id != '0') conversation.id: conversation,
      };

  Future<Map<String, ({ServerConversation? item, bool ok})>> _loadProcessingLifecycleResults(
    List<ServerConversation> pageItems,
    Set<String> processingIdsAtStart,
  ) async {
    final results = <String, ({ServerConversation? item, bool ok})>{
      for (final conversation in pageItems) conversation.id: (item: conversation, ok: true),
    };

    // Probe every card that was already tracked at refresh start, including
    // IDs present on this page. The page can carry an older status than the
    // detail endpoint; a failed probe remains inconclusive and preserves the
    // local card rather than replacing it with stale page data.
    final ids = processingIdsAtStart.toList();
    if (ids.isEmpty) return results;

    // Page entries are only a fallback for untracked rows. Tracked IDs must
    // start inconclusive until their lifecycle probe succeeds, otherwise a
    // probe that times out would silently retain a stale page status.
    for (final id in ids) {
      results[id] = (item: null, ok: false);
    }

    var nextIndex = 0;
    var deadlineExpired = false;
    Future<void> worker() async {
      while (true) {
        if (deadlineExpired || nextIndex >= ids.length) return;
        final id = ids[nextIndex++];
        ({ServerConversation? item, bool ok}) lifecycleResult;
        try {
          lifecycleResult = await _conversationLifecycleFetcher(id);
        } catch (_) {
          lifecycleResult = (item: null, ok: false);
        }
        // A timed-out worker may still complete later. Do not mutate the map
        // after the caller has received the fail-soft result.
        if (!deadlineExpired) results[id] = lifecycleResult;
      }
    }

    final workerCount = ids.length < ConversationProvider._processingLifecycleMaxConcurrency
        ? ids.length
        : ConversationProvider._processingLifecycleMaxConcurrency;
    final workers = List<Future<void>>.generate(workerCount, (_) => worker());
    try {
      await Future.wait(workers).timeout(ConversationProvider._processingLifecycleDeadline);
    } on TimeoutException {
      deadlineExpired = true;
      // Mark all unresolved probes inconclusive. Existing cards are retained
      // by reconciliation, while page-only rows still come from the page.
      for (final id in ids) {
        results[id] ??= (item: null, ok: false);
      }
    }
    return results;
  }

  void _reconcileProcessingConversations(
    Map<String, ({ServerConversation? item, bool ok})> lifecycleResults,
    Set<String> processingIdsAtStart,
    Set<String> pageConversationIds,
    Map<String, int> processingRevisionsAtStart,
    Map<String, ServerConversation> processingRowsAtStart,
    Map<String, String> pageStatusById,
  ) {
    final localPlaceholder = processingConversations.where((conversation) => conversation.id == '0').toList();
    final reconciled = <ServerConversation>[];
    localPlaceholder.removeWhere((placeholder) {
      if (placeholder is! OptimisticProcessingConversation) return false;
      final targetId = placeholder.targetConversationId;
      if (targetId == null || _processingStateRevisionById['0'] != processingRevisionsAtStart['0']) return false;
      if (_processingStateRevisionById[targetId] != processingRevisionsAtStart[targetId]) {
        // A live completion/start event superseded this detail snapshot.
        _cancelProcessingPlaceholderTimers();
        return true;
      }
      final result = lifecycleResults[targetId];
      if (result == null || !result.ok) return false;
      final current = result.item;
      if (current != null && _isActiveProcessingStatus(current.status) && _matchesActiveConversationFilters(current)) {
        // A real row supersedes the local attempt, including off-page rows.
        reconciled.add(current);
      }
      _cancelProcessingPlaceholderTimers();
      return true;
    });

    for (final existing in processingConversations.where((conversation) => conversation.id != '0')) {
      // A row added or replaced by websocket after this refresh began is newer
      // than the page/detail snapshot. Preserve that live object for this pass;
      // unrelated websocket events must not block reconciliation of this ID.
      if (!identical(processingRowsAtStart[existing.id], existing)) {
        if (_matchesActiveConversationFilters(existing)) reconciled.add(existing);
        continue;
      }
      final result = lifecycleResults[existing.id];
      if (result == null || !result.ok) {
        if (_matchesActiveConversationFilters(existing)) reconciled.add(existing);
        continue;
      }
      final current = result.item;
      if (current != null && _isActiveProcessingStatus(current.status) && _matchesActiveConversationFilters(current)) {
        if (reconciled.every((row) => row.id != current.id)) reconciled.add(current);
        continue;
      }
      if (processingIdsAtStart.contains(existing.id)) {
        final pageStatus = pageStatusById[existing.id];
        _clientTelemetry.noteProcessingRowLeft(
          id: existing.id,
          lifecycleOk: true,
          lifecycleStatus: current?.status.name,
          pageStatus: pageStatus,
        );
      }
    }

    for (final result in lifecycleResults.values) {
      final conversation = result.item;
      if (!result.ok || conversation == null || !_isActiveProcessingStatus(conversation.status)) continue;
      // Previously tracked IDs are owned by the live-list loop above. If a
      // websocket completion removed one while lifecycle GETs were in flight,
      // a stale detail response must not revive it here. This loop only admits
      // newly discovered active rows from the authoritative list page.
      if (_processingStateRevisionById[conversation.id] != processingRevisionsAtStart[conversation.id] ||
          processingIdsAtStart.contains(conversation.id) ||
          !pageConversationIds.contains(conversation.id) ||
          !_matchesActiveConversationFilters(conversation)) {
        continue;
      }
      if (reconciled.every((existing) => existing.id != conversation.id)) {
        reconciled.add(conversation);
      }
    }

    processingConversations = [...localPlaceholder, ...reconciled];
    _syncProcessingReconcileTimer();
  }
}
