// Ledger-owned, bounded foreground orphan adoption. Census stays off the capture
// queue; uncertainty retains bytes and no recovery path deletes audio.
part of 'local_wal_sync.dart';

const orphanRecoveryPassCap = 200;
const orphanRecoveryDailyCap = 400;

extension LocalOrphanRecovery on LocalWalSyncImpl {
  bool get _orphanForeground =>
      (_flushingTimer?.isActive ?? false) &&
      (_orphanForegroundOverride?.call() ?? WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed);

  void _maybeRecoverOrphanAudio() {
    if (!_orphanForeground || _headlessIndexLoad || _initialIndexAdmissionPending || !_walReady.isCompleted) return;
    final now = _now();
    if (_lastOrphanRecoveryWake != null && now.difference(_lastOrphanRecoveryWake!) < const Duration(minutes: 15)) {
      return;
    }
    _lastOrphanRecoveryWake = now;
    unawaited(recoverOrphanAudio());
  }

  /// Explicit recovery pass, separate from startup admission/native intake.
  /// Coalesced across resume/timer wakes. No audio mutation and no second uploader.
  Future<void> recoverOrphanAudio() => _orphanRecoveryInFlight ??= _recoverOrphanAudioOnce().whenComplete(() {
        _orphanRecoveryInFlight = null;
      });

  Future<void> _recoverOrphanAudioOnce() async {
    final generation = _sessionGeneration, uid = SharedPreferencesUtil().uid;
    RecordingOrphanCensus? census;
    final counts = <String, int>{};
    var result = 'completed';
    String? fence() {
      if (!_isCurrent(generation) || uid.isEmpty || uid != SharedPreferencesUtil().uid) return 'generation_changed';
      if (_headlessIndexLoad) return 'headless';
      if (_initialIndexAdmissionPending || !_walReady.isCompleted) return 'admission_pending';
      if (!_orphanForeground) return 'background';
      return null;
    }

    try {
      result = fence() ?? 'completed';
      if (result != 'completed') return;
      final off = await (_orphanRecoveryOffOverride ?? OrphanAudioRecoveryPolicy.isOff)();
      result = fence() ?? (off ? 'kill_switch' : 'completed');
      if (result != 'completed') return;
      final prefs = await SharedPreferences.getInstance();
      result = fence() ?? 'completed';
      if (result != 'completed') return;
      final documents = await getApplicationDocumentsDirectory();
      result = fence() ?? 'completed';
      if (result != 'completed') return;
      // Kept outside account preferences, which logout can clear. An interrupted
      // in-place fsynced write leaves an unreadable budget and blocks adoption.
      final budgetFile = File('${documents.path}/orphan_audio_recovery_budget.json');
      final budgetExists = await budgetFile.exists();
      result = fence() ?? 'completed';
      if (result != 'completed') return;
      if (!budgetExists) {
        await budgetFile.writeAsString('{}', flush: true);
        result = fence() ?? 'completed';
        if (result != 'completed') return;
      }
      if (_orphanCensusOverride != null) {
        census = await _orphanCensusOverride!();
      } else {
        String text(String key) => prefs.get(key) is String ? prefs.get(key)! as String : '';
        final configured = text('batchAudioDir');
        final legacy = prefs.get('flash_page_pending_uploads');
        // The full stat walk, JSON and frame parsing never hold _bufferQueue.
        census = await captureRecordingCensus(
            documents: documents.path,
            memoryBuckets: recordingInventorySnapshot,
            phoneSeconds: _now().millisecondsSinceEpoch ~/ 1000,
            currentOwner: uid,
            frameCache: _orphanFrameCache,
            additionalDirectories: configured.isEmpty ? [] : [configured],
            legacyFiles: legacy is List ? legacy.whereType<String>().toList() : [],
            legacyJobs: text('localRecordingJobs'),
            corruptLegacyJobs: text('localRecordingJobsCorrupt'));
      }
      result = fence() ?? 'completed';
      if (result != 'completed') return;
      _orphanFrameCache = census.frameCache;
      if (!census.complete || census.owner != uid) {
        result = 'incomplete_census';
        return;
      }
      final snapshot = census;
      final recoverable = snapshot.orphans.where((f) => f.classification == 'recoverable');
      counts['outsideDocuments'] = recoverable.where((f) => !snapshot.isDocumentsFile(f)).length;
      final candidates = recoverable.where(snapshot.isDocumentsFile).toList()
        ..sort((a, b) => a.info!.timerStart.compareTo(b.info!.timerStart));
      await _enqueueBuffer(() async {
        result = fence() ?? 'completed';
        if (result != 'completed') return;
        final off = await (_orphanRecoveryOffOverride ?? OrphanAudioRecoveryPolicy.isOff)();
        result = fence() ?? (off ? 'kill_switch' : 'completed');
        if (result != 'completed') return;
        // Reserve before publishing any row. A crash/save failure spends the
        // reservation conservatively, so restart cannot reset the daily cap.
        final budgetKey = sha256.convert(utf8.encode(uid)).toString();
        final now = _now().millisecondsSinceEpoch ~/ 1000;
        var spent = 0;
        final reservations = <Map<String, int>>[];
        final budgetRaw = await budgetFile.readAsString();
        result = fence() ?? 'completed';
        if (result != 'completed') return;
        Map<String, dynamic> budget;
        try {
          budget = Map<String, dynamic>.from(jsonDecode(budgetRaw) as Map);
        } catch (_) {
          result = 'budget_unavailable';
          return;
        }
        final raw = budget[budgetKey];
        if (raw != null) {
          try {
            for (final entry in raw as List) {
              final at = entry['at'] as int, count = entry['count'] as int;
              if (at > now || at < 0 || count <= 0 || count > orphanRecoveryDailyCap) {
                result = 'budget_unavailable';
                return;
              }
              if (now - at < 86400) {
                reservations.add({'at': at, 'count': count});
                spent += count;
              }
            }
          } catch (_) {
            // No released client has the pre-review fixed-window shape.
            // Unknown/torn formats retain audio rather than resetting capacity.
            result = 'budget_unavailable';
            return;
          }
        }
        final dailyRoom = max(0, orphanRecoveryDailyCap - spent);
        final pressureRoom = max(0, maxRetainedCaptureWalCount - _orphanPendingCount());
        final limit = min(orphanRecoveryPassCap, min(dailyRoom, pressureRoom));
        counts['dailyCap'] = max(0, candidates.length - dailyRoom);
        counts['pressureCap'] = max(0, min(candidates.length, dailyRoom) - pressureRoom);
        counts['passCap'] = max(0, min(candidates.length, min(dailyRoom, pressureRoom)) - orphanRecoveryPassCap);
        if (limit <= 0 || candidates.isEmpty) return;
        final reserved = min(limit, candidates.length);
        budget[budgetKey] = [
          ...reservations,
          {'at': now, 'count': reserved}
        ];
        await budgetFile.writeAsString(jsonEncode(budget), flush: true);
        result = fence() ?? 'completed';
        if (result != 'completed') return;
        if (!snapshot.sourcesUnchanged()) {
          result = 'sources_changed';
          return;
        }
        // Native intake can register while the budget write awaits; recheck all in-memory
        // buckets, ownership and pressure at commit. No await from stat to add.
        final buckets = recordingInventorySnapshot.values.expand((r) => r).toList();
        if (buckets.any((r) => r.owner != uid)) {
          result = 'sources_changed';
          return;
        }
        final refs = buckets.where((r) => r.filePath != null).map((r) => path.basename(r.filePath!)).toSet();
        final admitted = Set<Wal>.identity();
        void rollbackUnpublished() {
          if (_isCurrent(generation) && uid == SharedPreferencesUtil().uid) {
            _wals.removeWhere(admitted.contains);
          }
          counts['adopted'] = 0;
        }

        var room = min(reserved, max(0, maxRetainedCaptureWalCount - _orphanPendingCount()));
        for (final candidate in candidates.take(reserved)) {
          if (room <= 0) break;
          if (refs.contains(path.basename(candidate.filePath))) {
            counts['referenced'] = (counts['referenced'] ?? 0) + 1;
            continue;
          }
          if (!candidate.unchanged()) {
            counts['changed'] = (counts['changed'] ?? 0) + 1;
            continue;
          }
          final info = candidate.info!;
          final age = _now().millisecondsSinceEpoch ~/ 1000 - info.timerStart;
          if (age < 0 || age > orphanRecoveryWindowSeconds) {
            counts['expiredSinceCensus'] = (counts['expiredSinceCensus'] ?? 0) + 1;
            continue;
          }
          // Same external-file admission as addExternalWal, batched under the
          // ledger queue so one durable index transaction covers the pass.
          final wal = Wal(
              timerStart: info.timerStart,
              clockRun: candidate.clockRun,
              codec: info.codec,
              sampleRate: info.sampleRate,
              seconds: info.secondsFromFrameCount(candidate.frames),
              totalFrames: candidate.frames,
              storage: WalStorage.disk,
              status: WalStatus.miss,
              // Original per-file capture policy is lost. The existing held
              // recordings UI permits explicit upload/delete; onDeviceOnly
              // would also reject that deliberate manual upload in syncWal.
              holdForUser: true,
              filePath: path.basename(candidate.filePath),
              device: info.marker,
              ownerUid: uid,
              storageTotalBytes: candidate.bytes)
            ..frameSize = info.frameSize;
          _wals.add(wal);
          admitted.add(wal);
          refs.add(path.basename(candidate.filePath));
          counts['adopted'] = (counts['adopted'] ?? 0) + 1;
          room--;
        }
        if ((counts['adopted'] ?? 0) == 0) return;
        try {
          if (!await _saveWalsToFile(generation)) {
            rollbackUnpublished();
            result = fence() ?? 'failed';
            return;
          }
        } catch (_) {
          // Keep the conservative reservation, but let the next census retry
          // rows that never reached publication. No audio bytes are removed.
          rollbackUnpublished();
          rethrow;
        }
        result = fence() ?? 'completed';
        if (result != 'completed') return;
        heldRevision.value++;
        _notifyUpdated(generation);
      });
      result = fence() ?? result;
    } catch (_) {
      result = fence() ?? 'failed';
    } finally {
      _emitOrphanRecovery(census, counts, result);
    }
  }

  int _orphanPendingCount() =>
      [..._wals, ..._foreignWals, ..._retiredWals].where((w) => w.status != WalStatus.synced).length;

  void _emitOrphanRecovery(RecordingOrphanCensus? census, Map<String, int> skips, String result) {
    final summary = census?.summary['orphan_classification'] as Map?;
    int count(String group, String key, String unit) => (summary?[group]?[key]?[unit] as int?) ?? 0;
    final fields = <String, Object?>{
      'classification': summary,
      'counts': skips,
      'result': result,
      'census_complete': census?.complete ?? false
    };
    try {
      if (_orphanTelemetryOverride != null) {
        _orphanTelemetryOverride!(fields);
        return;
      }
      DebugLogManager.logEvent('orphan_audio_recovery', fields);
      const TypedEvents().emit(OrphanAudioRecovery(
        classWorkingCount: count('classes', 'working', 'count'),
        classWorkingBytes: count('classes', 'working', 'bytes'),
        classUnparseableCount: count('classes', 'unparseable', 'count'),
        classUnparseableBytes: count('classes', 'unparseable', 'bytes'),
        classRecoverableCount: count('classes', 'recoverable', 'count'),
        classRecoverableBytes: count('classes', 'recoverable', 'bytes'),
        classExpiredCount: count('classes', 'expired', 'count'),
        classExpiredBytes: count('classes', 'expired', 'bytes'),
        classOwnerUnknownCount: count('classes', 'owner_unknown', 'count'),
        classOwnerUnknownBytes: count('classes', 'owner_unknown', 'bytes'),
        age07Count: count('age_buckets', '0_7', 'count'),
        age07Bytes: count('age_buckets', '0_7', 'bytes'),
        age814Count: count('age_buckets', '8_14', 'count'),
        age814Bytes: count('age_buckets', '8_14', 'bytes'),
        age1528Count: count('age_buckets', '15_28', 'count'),
        age1528Bytes: count('age_buckets', '15_28', 'bytes'),
        age2945Count: count('age_buckets', '29_45', 'count'),
        age2945Bytes: count('age_buckets', '29_45', 'bytes'),
        ageOver45Count: count('age_buckets', 'over_45', 'count'),
        ageOver45Bytes: count('age_buckets', 'over_45', 'bytes'),
        ageUnknownCount: count('age_buckets', 'unknown', 'count'),
        ageUnknownBytes: count('age_buckets', 'unknown', 'bytes'),
        adopted: skips['adopted'] ?? 0,
        changed: skips['changed'] ?? 0,
        expiredSinceCensus: skips['expiredSinceCensus'] ?? 0,
        outsideDocuments: skips['outsideDocuments'] ?? 0,
        referenced: skips['referenced'] ?? 0,
        passCap: skips['passCap'] ?? 0,
        dailyCap: skips['dailyCap'] ?? 0,
        pressureCap: skips['pressureCap'] ?? 0,
        result: OrphanAudioRecoveryResult.values.firstWhere((v) => v.wireName == result),
        censusComplete: census?.complete ?? false,
      ));
    } catch (_) {/* Diagnostics never affect custody. */}
  }
}
