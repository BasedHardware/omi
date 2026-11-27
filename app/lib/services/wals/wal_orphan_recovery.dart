// Ledger-owned, bounded foreground orphan adoption. Census stays off the capture
// queue; uncertainty retains bytes and no recovery path deletes audio.
part of 'local_wal_sync.dart';

const orphanRecoveryPassCap = 200;
const orphanRecoveryDailyCap = 400;

// Validate the current serialized CustomSttConfig shape, without coercing or
// repairing any value. Future keys/types cannot silently become cloud consent.
bool _orphanCloudConfigKnown(Object? value) {
  const text = {'api_key', 'language', 'model', 'url', 'host', 'request_type', 'audio_field_name'};
  const fields = {'provider', 'send_raw_audio_to_omi', 'port', 'headers', 'params', 'schema', ...text};
  if (value is! Map || value.keys.any((key) => !fields.contains(key)) || value['provider'] != 'omi') return false;
  if (value['send_raw_audio_to_omi'] != null && value['send_raw_audio_to_omi'] != true) return false;
  if (text.any((key) => value[key] != null && value[key] is! String)) return false;
  final port = value['port'];
  if (port != null && (port is! int || port < 1 || port > 65535)) return false;
  final request = value['request_type'];
  if (request != null && !const {'multipart_form', 'raw_binary', 'json_base64', 'streaming'}.contains(request)) {
    return false;
  }
  for (final key in ['headers', 'params']) {
    final entries = value[key];
    if (entries != null &&
        (entries is! Map ||
            entries.entries.any((e) => e.key is! String || (e.key as String).isEmpty || e.value is! String))) {
      return false;
    }
  }
  final schema = value['schema'];
  if (schema != null) {
    const paths = {
      'segments_path',
      'segments_text_field',
      'segments_start_field',
      'segments_end_field',
      'segments_speaker_field',
      'segments_speaker_id_field',
      'segments_is_user_field',
      'segments_person_id_field',
      'segments_translations_field',
      'text_path'
    };
    if (schema is! Map ||
        schema.keys.any((key) => !paths.contains(key) && key != 'default_segment_duration') ||
        paths.any((key) => schema[key] != null && schema[key] is! String)) {
      return false;
    }
    final duration = schema['default_segment_duration'];
    if (duration != null && (duration is! num || !duration.isFinite || duration <= 0)) return false;
  }
  return true;
}

/// How often the orphan census may run while live audio streams (15 minutes otherwise).
const orphanRecoveryStreamingInterval = Duration(hours: 2);

/// Whether the orphan census may run now. It walks every file in Documents on the UI isolate (2.6 s
/// freezes on a heavy phone, 2026-11-21), so while live audio is arriving (a frame in the last
/// minute) it runs at most every two hours instead of every 15 minutes: a streaming pendant is not
/// interrupted by it each quarter hour, and it still runs.
@visibleForTesting
bool orphanRecoveryDue({required DateTime now, DateTime? lastRun, DateTime? lastLiveFrame}) {
  if (lastRun == null) return true;
  final streaming = lastLiveFrame != null && now.difference(lastLiveFrame) < const Duration(minutes: 1);
  return now.difference(lastRun) >= (streaming ? orphanRecoveryStreamingInterval : const Duration(minutes: 15));
}

extension LocalOrphanRecovery on LocalWalSyncImpl {
  /// Opaque, read-only derived framing for diagnostics; never export the cache.
  OrphanAudioFrameCache get orphanFrameCache => _orphanFrameCache;

  bool get _orphanForeground =>
      (_flushingTimer?.isActive ?? false) &&
      (_orphanForegroundOverride?.call() ?? WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed);

  void _maybeRecoverOrphanAudio() {
    if (!_orphanForeground || _headlessIndexLoad || _initialIndexAdmissionPending || !_walReady.isCompleted) return;
    if (!orphanRecoveryDueNow) return;
    final now = _now();
    _lastOrphanRecoveryWake = now;
    unawaited(recoverOrphanAudio().then((_) => reclaimOrphanAudio()));
  }

  /// Explicit recovery pass, separate from startup admission/native intake.
  /// Coalesced across resume/timer wakes. No audio mutation and no second uploader.
  /// Registered as lag work: the census walks every file in Documents (~168k on a heavy phone) and
  /// copies that inventory into its isolates from the UI isolate, so a stall it causes is named.
  Future<void> recoverOrphanAudio() => _orphanRecoveryInFlight ??= () {
        final work = lagWork.begin(LagWork.orphanCensus);
        return _recoverOrphanAudioOnce().whenComplete(() {
          lagWork.end(work);
          _orphanRecoveryInFlight = null;
        });
      }();

  Future<void> _recoverOrphanAudioOnce() async {
    final generation = _sessionGeneration, uid = SharedPreferencesUtil().uid;
    RecordingOrphanCensus? census;
    final counts = <String, int>{};
    var result = 'completed', published = false;
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
      final legacyPreferences = RecordingInventoryPreferences.capture(prefs.getKeys(), prefs.get);
      if (_orphanCensusOverride != null) {
        census = await _orphanCensusOverride!();
      } else {
        // The full stat walk, JSON and frame parsing never hold _bufferQueue.
        census = await captureRecordingCensus(
            documents: documents.path,
            memoryBuckets: recordingInventorySnapshot,
            phoneSeconds: _now().millisecondsSinceEpoch ~/ 1000,
            currentOwner: uid,
            frameCache: _orphanFrameCache,
            additionalDirectories: legacyPreferences.directories,
            legacyFiles: legacyPreferences.files,
            legacyJobs: legacyPreferences.jobs,
            corruptLegacyJobs: legacyPreferences.corruptJobs,
            legacyPreferencesComplete: legacyPreferences.complete);
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
        // A flag response can settle while the durable budget write awaits.
        final commitOff = await (_orphanRecoveryOffOverride ?? OrphanAudioRecoveryPolicy.isOff)();
        result = fence() ?? (commitOff ? 'kill_switch' : 'completed');
        if (result != 'completed') return;
        if (!legacyPreferences.matches(RecordingInventoryPreferences.capture(prefs.getKeys(), prefs.get)) ||
            !snapshot.sourcesUnchanged()) {
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
        // Case-folded, matching the census reserve and the reclaim unlink fence.
        final refs =
            buckets.where((r) => r.filePath != null).map((r) => path.basename(r.filePath!).toLowerCase()).toSet();
        // No await until publication: consent and memory are stable in this
        // isolate. Decode the settings once for the entire bounded admission.
        final holdForUser = snapshot.hasLocalOnlyHistory ||
            buckets.any((r) => r.onDeviceOnly || r.holdForUser) ||
            _orphanUploadNeedsHold(prefs);
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
          if (refs.contains(path.basename(candidate.filePath).toLowerCase())) {
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
              // David, 2026-11-17: automatic upload requires no local-only
              // history anywhere on this phone AND a cloud-permitting choice.
              // Read preferences and memory again after budget I/O, with no
              // await before publication. Held rows keep explicit user actions.
              holdForUser: holdForUser,
              recoveredOrphan: true,
              filePath: path.basename(candidate.filePath),
              device: info.marker,
              ownerUid: uid,
              storageTotalBytes: candidate.bytes)
            ..frameSize = info.frameSize;
          _wals.add(wal);
          admitted.add(wal);
          refs.add(path.basename(candidate.filePath).toLowerCase());
          counts['adopted'] = (counts['adopted'] ?? 0) + 1;
          room--;
        }
        if ((counts['adopted'] ?? 0) == 0) return;
        try {
          if (!await _saveWalsToFile(generation)) {
            rollbackUnpublished();
            // A concurrent lifecycle fence must not hide an actual save failure.
            result = 'failed';
            return;
          }
        } catch (_) {
          // Keep the conservative reservation, but let the next census retry
          // rows that never reached publication. No audio bytes are removed.
          rollbackUnpublished();
          rethrow;
        }
        if (!_isCurrent(generation) || uid != SharedPreferencesUtil().uid) {
          result = 'generation_changed';
          return;
        }
        // A successful save published these rows even if foreground/admission
        // changed during I/O. Publish the view revision within the same owner.
        published = true;
        heldRevision.value++;
        _notifyUpdated(generation);
      });
      result = published ? 'completed' : fence() ?? result;
    } catch (_) {
      result = 'failed';
    } finally {
      if (published) result = 'completed';
      _emitOrphanRecovery(census, counts, result);
    }
  }

  bool _orphanUploadNeedsHold(SharedPreferences prefs) {
    const localKeys = [
      'onDeviceTranscription.keepEverythingOnDevice',
      'onDeviceTranscription.saveLiveHours',
      'onDeviceOverflowActive'
    ];
    final consentKeys = ['customSttConfig', 'autoSyncOfflineRecordings', ...localKeys];
    if (prefs.getKeys().any((k) => consentKeys.any((name) => k.startsWith('$name.corrupt-')))) return true;
    final auto = prefs.get('autoSyncOfflineRecordings');
    if (auto != null && auto != true) return true;
    if (localKeys.any((k) => prefs.get(k) != null && prefs.get(k) != false)) return true;
    final value = prefs.get('customSttConfig');
    if (value != null && value is! String) return true;
    final raw = value as String? ?? '';
    if (raw.isNotEmpty) {
      try {
        // Read raw values: repairing getters discard wrong types and default
        // to cloud. Unknown or quarantined consent cannot authorize upload.
        final config = jsonDecode(raw);
        if (!_orphanCloudConfigKnown(config)) return true;
      } catch (_) {
        return true;
      }
    }
    // The live controller can keep audio local before its preference write lands.
    return LocalSttCustody.keepsPhoneAudio || OnDeviceTranscriptionController.instance.shouldKeepAudioLocal;
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
        result: OrphanAudioRecoveryResult.values
            .firstWhere((v) => v.wireName == result, orElse: () => OrphanAudioRecoveryResult.failed),
        censusComplete: census?.complete ?? false,
      ));
      const TypedEvents().emit(OrphanAudioReceiptless(
        phase: OrphanAudioReceiptlessPhase.recovery,
        receiptlessManagedCount: count('classes', 'receiptless_managed', 'count'),
        receiptlessManagedBytes: count('classes', 'receiptless_managed', 'bytes'),
        managedReceiptMissingSkipCount: 0,
        receiptScanTruncated: census?.summary['receipt_scan_truncated'] == true,
        censusComplete: census?.complete ?? false,
      ));
    } catch (_) {/* Diagnostics never affect custody. */}
  }
}
