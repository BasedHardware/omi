part of 'local_wal_sync.dart';

extension CaptureCommittedCustody on LocalWalSyncImpl {
  /// The socket supplies its opening owner and session. Never attribute a late
  /// receipt to whichever account happens to be active when the queue drains.
  Future<void> recordCustodyReceipt(MessageEvent event, {required String owner, String? recordingSessionId}) {
    final generation = _sessionGeneration;
    bool current() => _isCurrent(generation) && owner == _currentWalOwnerUid();
    return _enqueueBuffer(() async {
      if (owner.isEmpty || owner == 'legacy' || !current()) return;
      final intervals = await captureCommits.record(owner, event, recordingSessionId: recordingSessionId);
      if (!current() || intervals.isEmpty) return;
      await _persistCaptureCommits(generation, affected: (wal) {
        final start = wal.sourceFrameStart!;
        return intervals.any((range) =>
            range.root == wal.captureRoot &&
            range.epoch == wal.sourceClockEpoch &&
            start < range.end &&
            range.start < start + wal.totalFrames);
      });
    });
  }

  /// The buffer queue serializes journal updates, flushes, and confirmations.
  /// Compute decisions first so a slow audit cannot expose half a batch.
  Future<void> _persistCaptureCommits(int generation, {bool Function(Wal)? affected}) async {
    final owner = _currentWalOwnerUid();
    bool current() => _isCurrent(generation) && owner == _currentWalOwnerUid();
    if (!current() || owner.isEmpty || owner == 'legacy' || _initialIndexAdmissionPending) return;
    final candidates = _wals
        .where((wal) =>
            wal.ownerUid == owner &&
            wal.storage == WalStorage.disk &&
            _captureCommitEligible(wal) &&
            captureEvidenceWalClaimable(wal) &&
            (affected == null || affected(wal)))
        .toList();
    if (candidates.isEmpty) return;

    final release = await ClientRefactorFlags.custodyRelease();
    final verified = <Wal, Object>{};
    var agreeCovered = 0, agreePending = 0, disagree = 0, unknown = 0;
    for (final wal in candidates) {
      if (!current()) return;
      final identity = CaptureCommittedJournal.releaseIdentity(owner, wal);
      final decision = await captureCommits.evaluate(owner, wal);
      if (decision.audited == null) {
        unknown++;
      } else if (decision.covered != decision.audited) {
        disagree++;
      } else if (decision.covered) {
        agreeCovered++;
        if (release && identity != null) verified[wal] = identity;
      } else {
        agreePending++;
      }
    }
    if (!current()) return;
    // Immediately recheck membership and eligibility. In particular an uploader
    // may have reserved a row while the manifest digests were being checked.
    verified.removeWhere((wal, identity) =>
        !_activeWals.containsIdentity(wal) ||
        !_captureCommitEligible(wal) ||
        identity != CaptureCommittedJournal.releaseIdentity(owner, wal));
    final now = _now().millisecondsSinceEpoch ~/ 1000;
    for (final wal in verified.keys) {
      wal.status = WalStatus.synced;
      wal.syncedAt = now;
      wal.keptForTranscriptRecovery = false;
    }
    if (verified.isNotEmpty) {
      try {
        if (!await _saveWalsToFile(generation)) throw StateError('WAL index admission unavailable');
      } catch (_) {
        for (final wal in verified.keys) {
          if (_isTrackedWal(wal)) _keepForTranscriptRepair(wal);
        }
        rethrow;
      }
      if (!current()) return;
      _notifyUpdated(generation);
    }
    try {
      const TypedEvents().emit(WalCustodyAudit(
          agreeCovered: agreeCovered,
          agreePending: agreePending,
          disagree: disagree,
          unknown: unknown,
          released: verified.length));
    } catch (_) {/* Analytics availability never grants custody. */}
  }

  bool _captureCommitEligible(Wal wal) =>
      !wal.holdForUser &&
      !wal.onDeviceOnly &&
      !wal.isSyncing &&
      !_isDiscardedRecording(wal) &&
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
    bool allowTranscriptCoverageFallback = false,
  }) {
    final generation = _sessionGeneration;
    return _enqueueBuffer(() async {
      final useCommits = await ClientRefactorFlags.custodyRelease();
      if (!_isCurrent(generation)) return (released: 0, kept: 0);
      if (useCommits) await _persistCaptureCommits(generation);
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
        if (!_captureCommitEligible(wal)) continue;
        // Live Custom STT owns a separate, explicit transcript-confirmation contract.
        // Only the capture mode frozen at socket creation grants this fallback.
        final allowTranscript = !useCommits || allowTranscriptCoverageFallback && wal.ownerUid == _currentWalOwnerUid();
        final isCovered = allowTranscript &&
            spans != null &&
            walCoveredByTranscript(wal, spans, conversationStartSeconds ?? sessionStartSeconds);
        if (isCovered) {
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
          if (!await _saveWalsToFile(generation)) throw StateError('WAL index admission unavailable');
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
    });
  }
}
