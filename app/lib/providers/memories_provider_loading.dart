part of 'memories_provider.dart';

extension _MemoriesProviderLoading on MemoriesProvider {
  Future<GetMemoriesResult> _fetchMemoryPage({
    required int limit,
    required int offset,
    required bool thisDeviceOnly,
    String? cursor,
    MemoryReadView? view,
  }) {
    final cursorRequest = _fetchMemoriesCursorRequest;
    if (cursorRequest != null) {
      return cursorRequest(limit: limit, offset: offset, thisDeviceOnly: thisDeviceOnly, cursor: cursor, view: view);
    }
    // A caller-provided legacy fetcher has no cursor contract. The load loop
    // stops before reaching this branch with a non-null cursor, so this is only
    // used for the initial offset page.
    return _fetchMemoriesRequest(limit: limit, offset: offset, thisDeviceOnly: thisDeviceOnly);
  }

  Future<GetLedgerHistoryResult> _fetchHistoryPage({required int limit, required int offset, String? cursor}) {
    final cursorRequest = _fetchLedgerHistoryCursorRequest;
    if (cursorRequest != null) {
      return cursorRequest(limit: limit, offset: offset, cursor: cursor);
    }
    return _fetchLedgerHistoryRequest(limit: limit, offset: offset);
  }

  Future<void> _loadMemoriesInternal({int limit = 100}) async {
    final generation = _sessionGeneration;
    final loadSequence = ++_loadSequence;
    _beliefEnabled ??= memoryBeliefCapability;
    final serverView = _serverViewForCollection(_collectionView);
    final ledgerProjectionRevision = _ledgerProjectionRevision;
    // Snapshot the pending-deletion ID before any await: a refresh that
    // started during the undo window must still suppress the deleted item
    // even if _finalizeDeletion() clears the field while the fetch is in
    // flight.
    final tombstoneId = _pendingDeletionId;
    _loading = true;
    _notify();

    if (_filterThisDeviceOnly) {
      // Best-effort: if device-id hydration fails, fall through and load all
      // memories (local device filtering is skipped) rather than leaving
      // _loading stuck true, which was set just above.
      try {
        await _ensureClientDeviceInitialized();
      } catch (e) {
        Logger.error('MemoriesProvider: device init during load failed (non-fatal): $e');
      }
      if (generation != _sessionGeneration || loadSequence != _loadSequence) {
        return;
      }
    }

    // Page until a short page: backend no longer expands the first page to 5000
    // (prod GET /v3/memories 504s). Cap total fetch so a huge account cannot hang the UI.
    const maxPages = 20;
    final all = <Memory>[];
    final seenCurrent = <String>{};
    var offset = 0;
    String? memoryCursor;
    var currentTraversalComplete = false;
    var currentFetchCoversAll = false;
    var viewProtocolRestarts = 0;
    var deviceScopeSupported = true;
    var ledgerHistorySupported = false;
    var ledgerHistoryTruncated = false;
    var ledgerHistoryHasMore = false;
    var ledgerHistoryOffset = 0;
    String? ledgerHistoryNextCursor;
    void publishProvisional({bool failed = false}) {
      final effectiveTombstoneId = _pendingDeletionId ?? tombstoneId;
      _memories = effectiveTombstoneId != null
          ? all.where((memory) => memory.id != effectiveTombstoneId).toList()
          : List<Memory>.of(all);
      final pendingMemories = SharedPreferencesUtil().pendingMemories;
      for (var pending in pendingMemories) {
        if (pending.id != effectiveTombstoneId && !_memories.any((m) => m.id == pending.id)) {
          _memories.add(pending);
        }
      }
      SiriIntegration.current.queueUpsertMemories(_memories);
      _deviceScopeSupported = deviceScopeSupported;
      _loadFailed = failed;
      _loading = false;
      _hasLoaded = true;
      _setCategories();
    }

    try {
      for (var page = 0; page < maxPages; page++) {
        final requestedView = _beliefEnabled == true ? serverView : null;
        final result = await _fetchMemoryPage(
          limit: limit,
          // Cursor pages and offset pages are different protocols. The API
          // rejects a non-zero offset with a cursor, so reset the offset when a
          // server continuation marker takes over.
          offset: memoryCursor == null ? offset : 0,
          thisDeviceOnly: _filterThisDeviceOnly,
          cursor: memoryCursor,
          // Do not send a temporal selector until the capability probe has
          // confirmed it. A restart below binds the first cursor page to the
          // same selector used by every continuation page.
          view: requestedView,
        );
        if (generation != _sessionGeneration || loadSequence != _loadSequence) {
          return;
        }
        if (ledgerProjectionRevision != _ledgerProjectionRevision) {
          _loading = false;
          _hasLoaded = true;
          _notify();
          return;
        }
        if (!result.ok) {
          if (all.isNotEmpty) {
            // The retained partial projection is the same non-authoritative
            // shape as the final non-complete path: index what is shown so
            // Siri/search stay consistent with the visible rows.
            SiriIntegration.current.queueUpsertMemories(all);
            publishProvisional(failed: true);
            return;
          }
          _loadFailed = true;
          final effectiveTombstoneId = _pendingDeletionId ?? tombstoneId;
          final cached = SharedPreferencesUtil().cachedMemories;
          if (cached.isNotEmpty) {
            _memories = effectiveTombstoneId != null
                ? cached.where((memory) => memory.id != effectiveTombstoneId).toList()
                : cached;
            _setCategories();
          }
          _loading = false;
          _hasLoaded = true;
          _notify();
          return;
        }
        deviceScopeSupported = result.deviceScopeSupported;
        // A missing header is a capability reset. Do not let a prior true value
        // leak into a stable/older response on the next page or account.
        _beliefEnabled = result.beliefEnabled;
        final responseUsesTemporalView = result.beliefEnabled == true;
        if ((requestedView != null) != responseUsesTemporalView) {
          if (viewProtocolRestarts < 2) {
            viewProtocolRestarts++;
            all.clear();
            seenCurrent.clear();
            currentFetchCoversAll = false;
            offset = 0;
            memoryCursor = null;
            Logger.debug('MemoriesProvider: restarting memory read after capability/view change');
            continue;
          }
          Logger.warning(
              'MemoriesProvider: capability/view changed repeatedly; stopping before mixing cursor protocols');
          break;
        }
        // Scope belongs to the successful current-page response. The separate
        // ledger-history request may reset capability without broadening it.
        currentFetchCoversAll = result.beliefEnabled != true || requestedView == MemoryReadView.all;
        all.addAll(result.memories.where((memory) => seenCurrent.add(memory.id)));
        publishProvisional();
        // A truncated page is an honest partial response with no resumable cursor;
        // stop loading instead of continuing with an unstable offset.
        if (result.truncated) {
          if (result.truncated) {
            Logger.warning(
                'MemoriesProvider: server returned a truncated list; stopping at ${seenCurrent.length} rows');
          }
          break;
        }
        if (result.nextCursor != null) {
          if (_fetchMemoriesCursorRequest == null) {
            // A legacy injected fetcher cannot honor the server cursor. Do not
            // fall back to an offset after a cursor page; that would duplicate
            // or skip rows and falsely report a complete projection.
            Logger.warning('MemoriesProvider: server returned a cursor without a cursor fetcher');
            break;
          }
          if (result.nextCursor == memoryCursor) {
            Logger.warning('MemoriesProvider: server repeated the same memory cursor; stopping');
            break;
          }
          memoryCursor = result.nextCursor;
          continue;
        }
        // A cursor ending or a short offset page proves this owner/view was
        // exhausted. Truncated or capped traversals are additive only.
        if (memoryCursor != null || result.memories.length < limit) {
          currentTraversalComplete = true;
          break;
        }
        offset += result.memories.length;
      }
      // History is an additive owner-scoped projection, fetched independently
      // from the current list because GET /v3/memories intentionally filters
      // rejected and closed rows. Device-scoped history has no ratified server
      // contract, so the "This device" view remains current-only.
      if (!_filterThisDeviceOnly) {
        final seen = all.map((memory) => memory.id).toSet();
        const historyPageSize = 500;
        const maxHistoryPages = 10;
        var historyOffset = 0;
        var historyRowsLoaded = 0;
        String? historyCursor;
        for (var page = 0; page < maxHistoryPages; page++) {
          final result = await _fetchHistoryPage(limit: historyPageSize, offset: historyOffset, cursor: historyCursor);
          if (generation != _sessionGeneration || loadSequence != _loadSequence) {
            return;
          }
          if (ledgerProjectionRevision != _ledgerProjectionRevision) {
            _loading = false;
            _hasLoaded = true;
            _notify();
            return;
          }
          ledgerHistorySupported = result.supported;
          // Every history response is authoritative for the beta capability.
          // Missing/false headers reset useful-now filtering to stable behavior.
          _beliefEnabled = result.beliefEnabled;
          if (!result.supported) break;
          all.addAll(result.memories.where((memory) => seen.add(memory.id)));
          publishProvisional();
          historyRowsLoaded += result.memories.length;
          ledgerHistoryOffset += result.memories.length;
          ledgerHistoryNextCursor = result.nextCursor;
          if (result.nextCursor != null) {
            if (_fetchLedgerHistoryCursorRequest == null) {
              Logger.warning('MemoriesProvider: ledger history returned a cursor without a cursor fetcher');
              ledgerHistoryTruncated = true;
              ledgerHistoryHasMore = true;
              break;
            }
            historyCursor = result.nextCursor;
            ledgerHistoryTruncated = true;
            ledgerHistoryHasMore = true;
            continue;
          }
          if (result.truncated) {
            ledgerHistoryTruncated = true;
            ledgerHistoryHasMore = true;
            break;
          }
          // Once a cursor stream has started, switching back to offset paging
          // would duplicate or skip rows. A cursor page without a continuation
          // is complete even when it is shorter than the requested limit.
          if (historyCursor != null) {
            ledgerHistoryTruncated = false;
            ledgerHistoryHasMore = false;
            break;
          }
          if (result.memories.length < historyPageSize) break;
          historyOffset += result.memories.length;
          if (page == maxHistoryPages - 1) ledgerHistoryTruncated = true;
          if (page == maxHistoryPages - 1) ledgerHistoryHasMore = true;
        }
        if (ledgerHistoryTruncated) {
          Logger.warning('MemoriesProvider: ledger history is partial; loaded $historyRowsLoaded rows');
        }
      }
    } catch (e) {
      if (generation != _sessionGeneration || loadSequence != _loadSequence) {
        return;
      }
      if (ledgerProjectionRevision != _ledgerProjectionRevision) {
        _loading = false;
        _hasLoaded = true;
        _notify();
        return;
      }
      Logger.error('MemoriesProvider: memory load failed (${e.runtimeType})');
      if (all.isNotEmpty) {
        // Same non-authoritative consistency rule as the failed-result path:
        // index the rows the user can see so Siri/search match the screen.
        SiriIntegration.current.queueUpsertMemories(all);
        publishProvisional(failed: true);
      } else {
        _loadFailed = true;
        _loading = false;
        _hasLoaded = true;
        _notify();
      }
      return;
    }
    if (generation != _sessionGeneration ||
        loadSequence != _loadSequence ||
        ledgerProjectionRevision != _ledgerProjectionRevision) {
      if (generation == _sessionGeneration && loadSequence == _loadSequence) {
        _loading = false;
        _hasLoaded = true;
        _notify();
      }
      return;
    }
    // Keep an optimistic delete hidden throughout its undo window. Use the
    // snapshot taken before the fetch so a concurrent finalization that
    // clears _pendingDeletionId mid-fetch cannot reinsert the row.
    // Re-check _pendingDeletionId at apply time: if the user deleted a memory
    // after loadMemories() started (tombstoneId was null at snapshot), the
    // stale response still contains it and would reinsert the row.
    final currentTombstoneId = _pendingDeletionId;
    final effectiveTombstoneId = currentTombstoneId ?? tombstoneId;
    _memories = effectiveTombstoneId != null ? all.where((memory) => memory.id != effectiveTombstoneId).toList() : all;
    // The default useful-now/device views do not cover every indexed memory.
    // Only an exhausted, owner-wide all/current view may remove absent IDs.
    final siriMemoryFetchIsAuthoritative = currentTraversalComplete && !_filterThisDeviceOnly && currentFetchCoversAll;
    if (siriMemoryFetchIsAuthoritative) {
      SiriIntegration.current.queueReconcileMemories(_memories);
    } else {
      SiriIntegration.current.queueUpsertMemories(_memories);
    }
    _deviceScopeSupported = deviceScopeSupported;
    _ledgerHistorySupported = ledgerHistorySupported;
    _ledgerHistoryTruncated = ledgerHistoryTruncated;
    _ledgerHistoryHasMore = ledgerHistoryHasMore;
    _ledgerHistoryOffset = ledgerHistoryOffset;
    _ledgerHistoryNextCursor = ledgerHistoryNextCursor;
    _loadFailed = false;
    // Merge pending memories that haven't synced yet
    final pendingMemories = SharedPreferencesUtil().pendingMemories;
    for (var pending in pendingMemories) {
      if (pending.id != effectiveTombstoneId && !_memories.any((m) => m.id == pending.id)) {
        _memories.add(pending);
      }
    }
    // Persist the complete server projection, including optional temporal
    // fields, so restart/offline rendering does not silently lose the
    // server's assessment clock or evidence date.
    SharedPreferencesUtil().cachedMemories = List<Memory>.unmodifiable(_memories);
    _revertOperationIds.removeWhere(
      (memoryId, _) => !_memories.any((memory) => memory.id == memoryId && canRevertSupersededFact(memory)),
    );

    _loading = false;
    _hasLoaded = true;
    _setCategories();
  }
}
