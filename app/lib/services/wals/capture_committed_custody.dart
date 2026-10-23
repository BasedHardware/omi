part of 'local_wal_sync.dart';

extension CaptureCommittedCustody on LocalWalSyncImpl {
  /// Receipts are serialized with WAL buffer changes and durably recorded even in shadow.
  Future<void> recordCaptureCommitted(CaptureCommittedEvent event) {
    final generation = _sessionGeneration;
    final owner = _currentWalOwnerUid();
    return _enqueueBuffer(() async {
      if (owner.isEmpty || owner == 'legacy' || !_isCurrent(generation)) return;
      await captureCommits.record(owner, event);
      if (!_isCurrent(generation)) return;
      await _persistCaptureCommits(generation);
      if (!_isCurrent(generation)) return;
      _notifyUpdated(generation);
    });
  }

  Future<bool> _persistCaptureCommits(int generation, {bool onlyIfReleased = false}) async {
    final released = <Wal>[];
    try {
      await _applyCaptureCommits(generation, released);
      if (onlyIfReleased && released.isEmpty) return _isCurrent(generation);
      final saved = await _saveWalsToFile(generation);
      if (!saved) _revertCaptureCommits(released, generation);
      return saved;
    } catch (_) {
      _revertCaptureCommits(released, generation);
      rethrow;
    }
  }

  void _revertCaptureCommits(List<Wal> released, int generation) {
    if (!_isCurrent(generation)) return;
    for (final wal in released) {
      if (_wals.any((tracked) => identical(tracked, wal))) _keepForTranscriptRepair(wal);
    }
  }

  Future<void> _applyCaptureCommits(int generation, List<Wal> released) async {
    final owner = _currentWalOwnerUid();
    if (owner.isEmpty || owner == 'legacy') return;
    final release = await ClientRefactorFlags.custodyRelease();
    if (!_isCurrent(generation)) return;
    for (final wal in List<Wal>.of(_wals)) {
      if (!_captureCommitEligible(wal)) continue;
      final committed = await captureCommits.covers(owner, wal);
      if (!_isCurrent(generation)) return;
      ClientRefactorFlags.compare('custody_commit', committed == (wal.status == WalStatus.synced && wal.syncedAt > 0));
      if (release && committed) {
        wal.status = WalStatus.synced;
        wal.syncedAt = _now().millisecondsSinceEpoch ~/ 1000;
        wal.keptForTranscriptRecovery = false;
        released.add(wal);
      }
    }
    return;
  }

  bool _captureCommitEligible(Wal wal) =>
      !wal.holdForUser &&
      !wal.onDeviceOnly &&
      !wal.isSyncing &&
      (wal.storage == WalStorage.disk || wal.storage == WalStorage.mem) &&
      (wal.status == WalStatus.miss || wal.status == WalStatus.synced && wal.syncedAt == 0);

  /// Judges each stamped WAL of [conversationId] against the saved transcript: a covered WAL moves
  /// into synced retention (the `autoRemoveSyncedCopies` lifecycle) and is not uploaded — the saved
  /// text suppresses the repair upload, never deletes the copy; an uncovered WAL stays `miss`,
  /// marked `keptForTranscriptRecovery`, and uploads for repair. Without [transcriptSpans], or with
  /// an explicit [failClosedReason], every eligible stamped WAL fails closed into repair.
  Future<({int released, int kept})> confirmSessionTranscription(
    int sessionStartSeconds,
    String conversationId, {
    List<(int, int)>? transcriptSpans,
    int? conversationStartSeconds,
    String? failClosedReason,
  }) async {
    final generation = _sessionGeneration;
    final useCommits = await ClientRefactorFlags.custodyRelease();
    if (!_isCurrent(generation)) return (released: 0, kept: 0);
    // A stamped WAL can start before the session window — its timerStart is backdated from its
    // frame count — so the transcript evidence judges every stamped copy instead.
    final stamped = _wals.where((wal) => wal.conversationId == conversationId).toList();
    if (stamped.isEmpty) return (released: 0, kept: 0);

    final spans =
        failClosedReason == null && transcriptSpans != null && transcriptSpans.isNotEmpty ? transcriptSpans : null;
    final reason = failClosedReason ?? (spans != null ? null : 'no_spans');
    final nowSeconds = _now().millisecondsSinceEpoch ~/ 1000;
    final covered = <Wal>[], kept = <Wal>[];
    for (final wal in stamped) {
      // Only phone-side pending copies and transport-only synced ones (socket sends, never
      // server-confirmed) are judged; in-flight, durable and terminal copies never regress.
      final eligible = !wal.holdForUser &&
          !wal.isSyncing &&
          (wal.storage == WalStorage.disk || wal.storage == WalStorage.mem) &&
          (wal.status == WalStatus.miss || wal.status == WalStatus.synced && wal.syncedAt == 0);
      if (!eligible || useCommits && wal.onDeviceOnly) continue;
      final legacyCovered =
          spans != null && walCoveredByTranscript(wal, spans, conversationStartSeconds ?? sessionStartSeconds);
      final committed = await captureCommits.covers(_currentWalOwnerUid(), wal);
      if (!_isCurrent(generation)) return (released: 0, kept: 0);
      ClientRefactorFlags.compare('custody_release', legacyCovered == committed);
      // refactor: superseded by CaptureCommittedJournal when custody_capture_committed_release=true
      if (useCommits ? committed : legacyCovered) {
        wal.status = WalStatus.synced;
        wal.syncedAt = nowSeconds;
        wal.keptForTranscriptRecovery = false;
        covered.add(wal);
      } else {
        // An uncovered transport-only synced copy reclassifies to miss so
        // fail-closed recovery uploads it instead of status-skipping it.
        _keepForTranscriptRepair(wal);
        kept.add(wal);
      }
    }
    if (covered.isNotEmpty || kept.isNotEmpty) {
      try {
        await _saveWalsToFile(generation);
      } catch (_) {
        // The durable index never recorded the coverage, so covered copies fail closed too.
        if (_isCurrent(generation)) {
          covered.where((wal) => _wals.any((tracked) => identical(tracked, wal))).forEach(_keepForTranscriptRepair);
        }
        rethrow;
      }
    }
    if (_isCurrent(generation) && covered.isNotEmpty) _notifyUpdated(generation);
    _emitWalTranscriptCoverage(
      generation: generation,
      phase: 'confirmation',
      covered: covered,
      kept: kept,
      failClosedReason: reason,
    );
    return (released: 0, kept: kept.length);
  }
}
