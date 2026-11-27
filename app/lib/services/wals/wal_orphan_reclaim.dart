// Foreground ledger-owned reclaim. A tombstone records intent, never permission:
// every retry needs a new complete census and all commit fences again.
part of 'local_wal_sync.dart';

const orphanReclaimPassCap = 200;
const orphanReclaimBatchSize = 5;

extension LocalOrphanReclaim on LocalWalSyncImpl {
  Future<void> reclaimOrphanAudio() => _orphanReclaimInFlight ??= _reclaimOrphanAudioOnce().whenComplete(() {
        _orphanReclaimInFlight = null;
      });

  Future<void> _reclaimOrphanAudioOnce() async {
    final passStopwatch = Stopwatch()..start();
    final generation = _sessionGeneration, uid = SharedPreferencesUtil().uid;
    var result = 'completed', deleted = 0, bytes = 0;
    RecordingOrphanCensus? census;
    RandomAccessFile? lease;
    final skips = <String, int>{};
    void skip(String reason) => skips[reason] = (skips[reason] ?? 0) + 1;
    String? fence() {
      if (!_isCurrent(generation) || uid.isEmpty || uid != SharedPreferencesUtil().uid) return 'generation_changed';
      if (_headlessIndexLoad) return 'headless';
      if (_initialIndexAdmissionPending || !_walReady.isCompleted) return 'admission_pending';
      if (!_orphanForeground) return 'background';
      return null;
    }

    Future<bool> permitted() async {
      if (fence() case final reason?) {
        result = reason;
        return false;
      }
      final off = await (_orphanReclaimOffOverride ?? OrphanAudioReclaimPolicy.isOff)();
      final blocked = fence() ?? (off ? 'kill_switch' : null);
      if (blocked != null) {
        result = blocked;
        return false;
      }
      // A successful later batch cannot erase an earlier source fence.
      return true;
    }

    try {
      if (!await permitted()) return;
      final documents = await getApplicationDocumentsDirectory();
      if (fence() case final reason?) {
        result = reason;
        return;
      }
      final journalDirectory = Directory('${documents.path}/orphan_audio_reclaim');
      await journalDirectory.create();
      if (fence() case final reason?) {
        result = reason;
        return;
      }
      // Non-blocking advisory lease for cooperating processes. The foreground
      // singleton coalesces calls; headless engines are excluded above. This OS
      // lock does not serialize isolates within one process.
      lease = await File('${journalDirectory.path}/writer.lock').open(mode: FileMode.append);
      await lease.lock(FileLock.exclusive);
      if (fence() case final reason?) {
        result = reason;
        return;
      }
      final journal = File('${journalDirectory.path}/tombstones.json');
      final entries = <Map<String, dynamic>>[];
      if (await journal.exists()) {
        if (await journal.length() > 256 * 1024) {
          result = 'journal_unavailable';
          return;
        }
        final Object? decoded;
        try {
          decoded = jsonDecode(await journal.readAsString());
        } on FormatException {
          // Torn JSON is a journal problem, distinct from an I/O failure in telemetry.
          result = 'journal_unavailable';
          return;
        }
        if (decoded is! Map ||
            decoded['version'] != 1 ||
            decoded['entries'] is! List ||
            (decoded['entries'] as List).length > 200) {
          result = 'journal_unavailable';
          return;
        }
        for (final entry in decoded['entries'] as List) {
          if (entry is! Map || entry['key'] is! String || !const {'pending', 'completed'}.contains(entry['state'])) {
            result = 'journal_unavailable';
            return;
          }
          entries.add(Map<String, dynamic>.from(entry));
        }
      }
      if (fence() case final reason?) {
        result = reason;
        return;
      }
      final prefs = await SharedPreferences.getInstance();
      final preferences = RecordingInventoryPreferences.capture(prefs.getKeys(), prefs.get);
      final legacyReferenceNames = await preferences.fileReferenceNames();
      if (fence() case final reason?) {
        result = reason;
        return;
      }
      census = await (_orphanCensusOverride?.call() ??
          captureRecordingCensus(
              documents: documents.path,
              memoryBuckets: recordingInventorySnapshot,
              phoneSeconds: _now().millisecondsSinceEpoch ~/ 1000,
              currentOwner: uid,
              frameCache: _orphanFrameCache,
              additionalDirectories: preferences.directories,
              legacyFiles: preferences.files,
              legacyJobs: preferences.jobs,
              corruptLegacyJobs: preferences.corruptJobs,
              legacyPreferencesComplete: preferences.complete));
      if (fence() case final reason?) {
        result = reason;
        return;
      }
      final snapshot = census;
      // Ownership proof is intentionally NOT required. Foreign/held references
      // reserve their own files; all accounts share the same reclaim age rule.
      if (!snapshot.complete || snapshot.summary['memory_snapshot_available'] != true || !preferences.complete) {
        result = 'incomplete_census';
        return;
      }
      _orphanFrameCache = snapshot.frameCache;
      final candidates = <OrphanAudioFile>[];
      for (final file in snapshot.orphans) {
        final reason = !snapshot.isDocumentsFile(file) ? 'outside_documents' : file.reclaimSkipReason(_now());
        if (reason != null) {
          skip(reason);
        } else {
          candidates.add(file);
        }
      }
      candidates.sort((a, b) => a.modifiedUs.compareTo(b.modifiedUs));
      skips['pass_cap'] = max(0, candidates.length - orphanReclaimPassCap);
      final bounded = candidates.take(orphanReclaimPassCap).toList();

      // Flushed intent is prepared off the capture queue. It grants no authority:
      // after this I/O each file still needs the complete synchronous commit fence.
      Future<void> checkpoint() async {
        final temp = File('${journal.path}.tmp');
        await temp.writeAsString(jsonEncode({'version': 1, 'entries': entries}), flush: true);
        await temp.rename(journal.path);
      }

      for (var start = 0; start < bounded.length; start += orphanReclaimBatchSize) {
        if (!await permitted()) return;
        final batch = bounded.skip(start).take(orphanReclaimBatchSize).toList();
        final intents = <OrphanAudioFile, Map<String, dynamic>>{};
        for (final file in batch) {
          final key = sha256
              .convert(
                  utf8.encode('${path.basename(file.filePath)}:${file.bytes}:${file.modifiedUs}:${file.changedUs}'))
              .toString();
          entries.removeWhere((entry) => entry['key'] == key);
          while (entries.length >= 200) {
            entries.removeAt(0);
          }
          final entry = <String, dynamic>{
            'key': key,
            'bytes': file.bytes,
            'mtime_us': file.modifiedUs,
            'at_us': _now().microsecondsSinceEpoch,
            'state': 'pending'
          };
          entries.add(entry);
          intents[file] = entry;
        }
        await checkpoint();
        await _enqueueBuffer(() async {
          // A capture operation may have held the queue after the outer read.
          // Refresh the resolved flag after that wait and the durable intent I/O.
          if (!await permitted()) return;
          for (final file in batch) {
            String? changed() {
              if (fence() case final reason?) return reason;
              if (!preferences.matches(RecordingInventoryPreferences.capture(prefs.getKeys(), prefs.get)) ||
                  !snapshot.sourcesUnchanged()) {
                return 'sources_changed';
              }
              // Legacy pending paths can use a container/directory alias. Reserve
              // their basenames conservatively even when census path strings differ.
              if (legacyReferenceNames.contains(path.basename(file.filePath).toLowerCase())) {
                return 'referenced';
              }
              if (recordingInventorySnapshot.values.expand((rows) => rows).any((row) =>
                  row.filePath != null &&
                  path.basename(row.filePath!).toLowerCase() == path.basename(file.filePath).toLowerCase())) {
                return 'referenced';
              }
              if (!file.unchanged()) return 'file_changed';
              return file.reclaimSkipReason(_now());
            }

            final sidecar = File(nativeBatchGeolocationSidecarPath(file.filePath));
            // omi-perf-allow: sync-file-io -- One sidecar type check per candidate; never follow a link for deletion.
            final sidecarType = FileSystemEntity.typeSync(sidecar.path, followLinks: false);
            if (sidecarType != FileSystemEntityType.notFound && sidecarType != FileSystemEntityType.file) {
              skip('sidecar_type');
              continue;
            }
            _orphanReclaimAfterTombstone?.call();
            // Revalidate AFTER the durable write. No await through either
            // unlink, so another queued producer cannot register in this gap.
            final reason = changed();
            if (reason != null) {
              skip(reason);
              if (reason == 'sources_changed') result = reason;
              continue;
            }
            // Sidecar first: a crash after the audio unlink cannot strand it.
            // omi-perf-allow: sync-file-io -- At most five small destructive transactions per capture-queue turn, all fenced and journaled.
            if (sidecarType == FileSystemEntityType.file) sidecar.deleteSync();
            // omi-perf-allow: sync-file-io -- One fenced audio unlink after durable intent, with no async reference race.
            File(file.filePath).deleteSync();
            deleted++;
            bytes += file.bytes;
            snapshot.acknowledgeReclaimUnlink();
            intents[file]!['state'] = 'completed';
          }
        });
        // Completion is audit state, never replay authority. A crash here leaves
        // pending intent; fresh census proof makes restart idempotent.
        await checkpoint();
        if (fence() case final reason?) {
          result = reason;
          return;
        }
        // Give waiting capture/intake work a turn between bounded batches.
        await Future<void>.delayed(Duration.zero);
      }
    } catch (_) {
      // A concurrent lifecycle fence must not hide an actual I/O/transaction failure.
      result = 'failed';
    } finally {
      await lease?.close();
      final fields = <String, Object?>{
        'deleted_files': deleted,
        'deleted_bytes': bytes,
        'skips': skips,
        'result': result,
        'census_complete': census?.complete ?? false,
        // Census plus reclaim wall time: the ramp gate measures this on David's device first.
        'duration_ms': passStopwatch.elapsedMilliseconds
      };
      try {
        if (_orphanReclaimTelemetry != null) {
          _orphanReclaimTelemetry!(fields);
        } else {
          DebugLogManager.logEvent('orphan_audio_reclaim', fields);
          const TypedEvents().emit(OrphanAudioReclaim(
              deletedFiles: deleted,
              deletedBytes: bytes,
              working: skips['working'] ?? 0,
              unknownCaptureTime: skips['unknown_capture_time'] ?? 0,
              captureTooYoung: skips['capture_too_young'] ?? 0,
              mtimeTooYoung: skips['mtime_too_young'] ?? 0,
              outsideDocuments: skips['outside_documents'] ?? 0,
              passCap: skips['pass_cap'] ?? 0,
              sourcesChanged: skips['sources_changed'] ?? 0,
              referenced: skips['referenced'] ?? 0,
              fileChanged: skips['file_changed'] ?? 0,
              sidecarType: skips['sidecar_type'] ?? 0,
              durationMs: passStopwatch.elapsedMilliseconds,
              result: OrphanAudioReclaimResult.values
                  .firstWhere((v) => v.wireName == result, orElse: () => OrphanAudioReclaimResult.failed),
              censusComplete: census?.complete ?? false));
          final classification = census?.summary['orphan_classification'] as Map?;
          final classes = classification?['classes'] as Map?;
          final receiptless = classes?['receiptless_managed'] as Map?;
          const TypedEvents().emit(OrphanAudioReceiptless(
            phase: OrphanAudioReceiptlessPhase.reclaim,
            receiptlessManagedCount: receiptless?['count'] as int? ?? 0,
            receiptlessManagedBytes: receiptless?['bytes'] as int? ?? 0,
            managedReceiptMissingSkipCount: skips['managed_receipt_missing'] ?? 0,
            receiptScanTruncated: census?.summary['receipt_scan_truncated'] == true,
            censusComplete: census?.complete ?? false,
          ));
        }
      } catch (_) {/* Aggregate diagnostics never grant or revoke deletion authority. */}
    }
  }
}
