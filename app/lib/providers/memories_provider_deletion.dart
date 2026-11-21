part of 'memories_provider.dart';

/// One owner/session-bound Undo or in-flight request. Replacing a toast does
/// not replace the earlier request's suppression, rollback or failure callback.
class _MemoryDeletion {
  _MemoryDeletion(this.memory, this.ownerUid, this.generation, this.onFailure);

  final Memory memory;
  Memory? serverMemory;
  final String ownerUid;
  final int generation;
  final VoidCallback? onFailure;
  Timer? timer;
  Future<void>? request;
}

extension _MemoriesProviderDeletion on MemoriesProvider {
  bool _ownsMemoryDeletion(_MemoryDeletion deletion) =>
      deletion.generation == _memoryDeletionGeneration &&
      deletion.ownerUid.isNotEmpty &&
      deletion.ownerUid == SharedPreferencesUtil().uid;

  Set<String> get _hiddenMemoryIds => {
        ..._memoryDeletions.keys,
        for (final deletion in _memoryDeletions.values)
          if (deletion.serverMemory != null) deletion.serverMemory!.id,
        ..._confirmedMemoryDeletes,
        ...SharedPreferencesUtil().confirmedMemoryDeletionIds,
      };

  bool _memoryIsVisible(Memory memory) => !_hiddenMemoryIds.contains(memory.id);

  List<Memory> _visibleMemories(Iterable<Memory> rows) {
    final hidden = _hiddenMemoryIds;
    return rows.where((row) => !hidden.contains(row.id)).toList();
  }

  Future<void> _stageMemoryDeletion(Memory memory, {VoidCallback? onFailure}) async {
    final ownerUid = SharedPreferencesUtil().uid;
    if (_memoryDeletesDisposed || ownerUid.isEmpty || memory.uid != ownerUid || !_memoryIsVisible(memory)) return;
    final previous = _undoDeletionId;
    if (previous != null) unawaited(_commitMemoryDeletion(previous));
    final deletion = _MemoryDeletion(memory, ownerUid, _memoryDeletionGeneration, onFailure);
    _memoryDeletions[memory.id] = deletion;
    _undoDeletionId = memory.id;
    deletion.timer = Timer(MemoriesProvider.pendingDeletionWindow, () => _commitMemoryDeletion(memory.id));
    _memories.removeWhere((row) => row.id == memory.id);
    _setCategories();
    SiriIntegration.current.queueDelete('memory', memory.id);
    _notify();
  }

  Future<void> _commitMemoryDeletion(String? id) {
    final deletion = _memoryDeletions[id];
    if (deletion == null || !_ownsMemoryDeletion(deletion)) return Future.value();
    if (deletion.request != null) return deletion.request!;
    // Claim before any await: timer, replaced toast and explicit commit join
    // one irreversible request. Undo can only restore a still-staged row.
    final completion = Completer<void>();
    deletion.request = completion.future;
    deletion.timer?.cancel();
    if (_undoDeletionId == id) _undoDeletionId = null;
    _finishMemoryDeletion(deletion).then(completion.complete, onError: completion.completeError);
    return completion.future;
  }

  Future<void> _finishMemoryDeletion(_MemoryDeletion deletion) async {
    final prefs = SharedPreferencesUtil();
    final pendingId = deletion.memory.id;
    // A draft may already be crossing POST /memories. Wait for its real ID,
    // then delete that row; dropping the local draft alone would orphan it.
    final creation = _memoryCreations[pendingId];
    if (creation != null) deletion.serverMemory = await creation;
    if (!_ownsMemoryDeletion(deletion)) return;
    final deletedMemory = deletion.serverMemory ?? deletion.memory;
    final id = deletedMemory.id;
    var succeeded = true;
    var persistenceFailed = false;
    final localOnly = deletion.serverMemory == null && prefs.pendingMemories.any((row) => row.id == pendingId);
    if (!localOnly) {
      try {
        succeeded = await (_deleteMemoryRequest?.call(id) ??
            deleteMemoryServer(id, canSend: () => _ownsMemoryDeletion(deletion)));
      } catch (error) {
        Logger.debug('MemoriesProvider: memory deletion failed: ${error.runtimeType}');
        succeeded = false;
      }
    }
    // Both rollback and success are private owner-bound publications. A UID
    // matching again after sign-out does not revive the original generation.
    if (!_ownsMemoryDeletion(deletion)) return;
    _ledgerProjectionRevision++;
    if (succeeded) {
      _confirmedMemoryDeletes.addAll([pendingId, id]);
      for (final deletedId in {pendingId, id}) {
        try {
          await prefs.recordConfirmedMemoryDelete(deletedId, ownerUid: deletion.ownerUid);
        } catch (error) {
          Logger.debug('MemoriesProvider: memory deletion persistence failed: ${error.runtimeType}');
          persistenceFailed = true;
        }
      }
      if (!_ownsMemoryDeletion(deletion)) return;
    }
    if (_memoryDeletesDisposed) {
      if (!succeeded) SiriIntegration.current.queueUpsertMemories([deletedMemory], restoreDeleted: true);
      return;
    }
    _memoryDeletions.remove(pendingId);
    if (!succeeded) {
      if (!_memories.any((row) => row.id == id)) _memories.add(deletedMemory);
      SiriIntegration.current.queueUpsertMemories([deletedMemory], restoreDeleted: true);
    }
    _setCategories();
    _notify();
    if (!succeeded || persistenceFailed) deletion.onFailure?.call();
  }

  bool _undoMemoryDeletion(String? id) {
    final deletion = _memoryDeletions[id];
    if (deletion == null || deletion.request != null || !_ownsMemoryDeletion(deletion)) return false;
    deletion.timer?.cancel();
    _memoryDeletions.remove(id);
    if (_undoDeletionId == id) _undoDeletionId = null;
    _ledgerProjectionRevision++;
    final restored = deletion.serverMemory ?? deletion.memory;
    if (!_memories.any((row) => row.id == restored.id)) _memories.add(restored);
    _setCategories();
    SiriIntegration.current.queueUpsertMemories([restored], restoreDeleted: true);
    _notify();
    return true;
  }

  Future<Memory?> _trackMemoryCreation(Memory draft) async {
    final existing = _memoryCreations[draft.id];
    if (existing != null) return existing;
    final generation = _sessionGeneration;
    final ownerUid = draft.uid;
    final request = Future<Memory?>.sync(() =>
            _createMemoryRequest?.call(draft.content, draft.visibility.name, draft.category.name) ??
            createMemoryServer(draft.content, draft.visibility.name, draft.category.name,
                canSend: () => generation == _sessionGeneration && SharedPreferencesUtil().uid == ownerUid))
        .catchError((Object error) {
      Logger.debug('MemoriesProvider: memory sync failed: ${error.runtimeType}');
      return null;
    });
    _memoryCreations[draft.id] = request;
    try {
      return await request;
    } finally {
      if (identical(_memoryCreations[draft.id], request)) _memoryCreations.remove(draft.id);
    }
  }

  void _applyCreatedMemory(String pendingId, Memory serverMemory) {
    final deletion = _memoryDeletions[pendingId];
    if (deletion != null) {
      deletion.serverMemory = serverMemory;
      _ledgerProjectionRevision++;
      return;
    }
    final idx = _memories.indexWhere((row) => row.id == pendingId);
    if (idx != -1) _memories[idx] = serverMemory;
    _ledgerProjectionRevision++;
    _inFlightLoad = null;
    final prefs = SharedPreferencesUtil();
    prefs.cachedMemories = [
      ...prefs.cachedMemories.where((row) => row.id != pendingId && row.id != serverMemory.id),
      serverMemory,
    ];
    SiriIntegration.current.queueUpsertMemories([serverMemory]);
  }

  void _clearMemoryDeletions({bool retireSession = true}) {
    if (retireSession) _memoryDeletionGeneration++;
    for (final deletion in _memoryDeletions.values) {
      deletion.timer?.cancel();
    }
    _memoryDeletions.clear();
    _memoryCreations.clear();
    _confirmedMemoryDeletes.clear();
    _undoDeletionId = null;
  }
}
