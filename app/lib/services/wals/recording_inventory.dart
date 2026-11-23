import 'live_wal_receipt.dart';
import 'dart:convert';
import 'dart:io';
import 'dart:math' show min;
import 'dart:typed_data';

import 'package:path/path.dart' as path;
import 'package:crypto/crypto.dart';
import 'package:omi/backend/schema/capture_committed_event.dart';
import 'package:omi/services/wals/capture_committed_journal.dart';
import 'package:omi/utils/batch_recording.dart';

import 'package:omi/utils/off_ui_isolate.dart';

part 'orphan_audio_classifier.dart';
part 'recording_inventory_sources.dart';

/// Internal metadata only. Paths/owners are used to correlate locally and are
/// NEVER returned by the export. No audio, titles or transcripts are read.
class RecordingInventoryRow {
  const RecordingInventoryRow(
      {required this.status,
      required this.captureSeconds,
      required this.audioSeconds,
      required this.indexBytes,
      required this.disk,
      this.filePath,
      this.owner,
      this.rebase = true,
      this.onDeviceOnly = false,
      this.holdForUser = false});
  final String status;
  final int? captureSeconds;
  final double? audioSeconds;
  final int indexBytes;
  final bool disk;
  final String? filePath;
  final String? owner;
  final bool rebase;
  final bool onDeviceOnly, holdForUser;
}

/// Concurrent stats per batch while walking a recordings directory.
const _statConcurrency = 64;

class _Metadata {
  _Metadata(this.filePath, this.kind, this.bytes, this.modifiedUs, this.changedUs);
  final String filePath, kind;
  final int bytes, modifiedUs, changedUs;
  int get modifiedMs => modifiedUs ~/ 1000;
  int get changedMs => changedUs ~/ 1000;
}

class _Decoded {
  _Decoded(this.rows, this.error, {this.loaderEvents = const [], this.invalidRows = 0});
  final List<RecordingInventoryRow> rows;
  final String? error;
  final List<Map<String, Object?>> loaderEvents;
  final int invalidRows;
}

const _statuses = {
  'inProgress',
  'miss',
  'uploaded',
  'synced',
  'corrupted',
  'outsideRecoveryWindow',
  'unsupportedAudio',
  'uploadRejected'
};

int? _integer(Object? value) => value is int ? value : null;
String? _string(Object? value) => value is String ? value : null;

int? _filenameTime(String name) {
  final token =
      RegExp(r'_(-?\d+(?:\.\d+)?)(?:_u\d{1,9})?\.bin(?:\.part|\.torn)?$').firstMatch(path.basename(name))?.group(1);
  final value = token == null ? null : double.tryParse(token);
  if (value == null || !value.isFinite) return null;
  return (value >= 100000000000 ? value / 1000 : value).floor();
}

RecordingInventoryRow _row(Map row) {
  final frames = _integer(row['total_frames']) ?? 0;
  final seconds = row['seconds'];
  final codec = _string(row['codec']) ?? '';
  final duration = frames > 0
      ? frames / (codec.contains('320') ? 50 : 100)
      : seconds is num && seconds.isFinite && seconds >= 0
          ? seconds.toDouble()
          : null;
  return RecordingInventoryRow(
      status: _string(row['status']) ?? 'unknown',
      captureSeconds: _integer(row['timer_start']),
      audioSeconds: duration,
      indexBytes: (_integer(row['storage_total_bytes']) ?? 0).clamp(0, 1 << 62),
      disk: row['storage'] == 'disk',
      filePath: _string(row['file_path']),
      owner: _string(row['owner_uid']),
      onDeviceOnly: row['on_device_only'] != null && row['on_device_only'] != false,
      holdForUser: row['hold_for_user'] != null && row['hold_for_user'] != false);
}

bool _audio(String name) =>
    name.startsWith('audio_') &&
    (name.endsWith('.bin') || name.endsWith('.bin.part') || name.endsWith('.bin.torn') || name.endsWith('.wav'));

String? _reference(RecordingInventoryRow row, String documents) {
  final name = row.filePath;
  if (name == null || name.isEmpty) return null;
  return path.normalize(row.rebase
      ? path.join(documents, path.basename(name))
      : path.isAbsolute(name)
          ? name
          : path.join(documents, name));
}

Map<String, Object?> _summarize(
    List<RecordingInventoryRow> rows, int phone, String uid, String documents, Map<String, _Metadata> audio) {
  final statuses = <String, int>{}, clocks = <String, int>{}, owners = <String, int>{};
  var seconds = 0.0, bytes = 0, fileBytes = 0, missing = 0, noReference = 0, unknownDuration = 0;
  int? oldest, newest, oldestModified, newestModified;
  for (final row in rows) {
    final status = _statuses.contains(row.status) ? row.status : 'unknown';
    statuses[status] = (statuses[status] ?? 0) + 1;
    final ts = row.captureSeconds;
    final clock = ts == null
        ? 'unknown'
        : ts <= 0
            ? 'zero'
            : ts < 1704067200
                ? 'before_2024'
                : ts > phone + 86400
                    ? 'future'
                    : 'plausible';
    clocks[clock] = (clocks[clock] ?? 0) + 1;
    final owner = row.owner == null || row.owner!.isEmpty
        ? 'unstamped'
        : row.owner == 'legacy'
            ? 'legacy'
            : uid.isEmpty
                ? 'unresolved'
                : row.owner == uid
                    ? 'current'
                    : 'foreign';
    owners[owner] = (owners[owner] ?? 0) + 1;
    if (ts != null) {
      oldest = oldest == null || ts < oldest ? ts : oldest;
      newest = newest == null || ts > newest ? ts : newest;
    }
    final duration = row.audioSeconds;
    if (duration != null && duration.isFinite && duration >= 0) {
      seconds += duration;
    } else {
      unknownDuration++;
    }
    bytes += row.indexBytes;
    if (row.disk || row.filePath != null) {
      final ref = _reference(row, documents);
      if (ref == null) {
        noReference++;
        continue;
      }
      final file = audio[ref];
      if (file == null) {
        missing++;
        continue;
      }
      fileBytes += file.bytes;
      oldestModified = oldestModified == null || file.modifiedMs < oldestModified ? file.modifiedMs : oldestModified;
      newestModified = newestModified == null || file.modifiedMs > newestModified ? file.modifiedMs : newestModified;
    }
  }
  return {
    'rows': rows.length,
    'by_status': statuses,
    'by_capture_time': clocks,
    'by_owner_class': owners,
    'audio_seconds_sum': seconds,
    'unknown_duration_rows': unknownDuration,
    'index_bytes_sum': bytes,
    'existing_file_bytes_sum': fileBytes,
    'rows_with_missing_file': missing,
    'rows_without_file_reference': noReference,
    'oldest_capture_seconds': oldest,
    'newest_capture_seconds': newest,
    'oldest_file_modified_ms': oldestModified,
    'newest_file_modified_ms': newestModified,
    'oldest_creation_ms': null,
    'newest_creation_ms': null
  };
}

/// Async metadata reads never acquire the WAL writer/custody locks. JSON decode
/// and all large correlation/aggregation run off the UI isolate. Never call the
/// production loader here: it quarantines, repairs, recovers and writes indexes.
Future<RecordingOrphanCensus> captureRecordingCensus(
    {required String documents,
    required Map<String, List<RecordingInventoryRow>> memoryBuckets,
    required int phoneSeconds,
    String currentOwner = '',
    List<String> additionalDirectories = const [],
    List<String> legacyFiles = const [],
    String legacyJobs = '',
    String corruptLegacyJobs = '',
    bool legacyPreferencesComplete = true,
    OrphanAudioFrameCache frameCache = const OrphanAudioFrameCache.empty(),
    int? freeBytes}) async {
  final started = DateTime.now().millisecondsSinceEpoch;
  final roots =
      {path.normalize(documents), ...additionalDirectories.where((p) => p.isNotEmpty).map(path.normalize)}.toList();
  final audio = <String, _Metadata>{}, metadata = <_Metadata>[];
  final directoryErrors = <int>[];
  final sourceDirectories = <String, FileStat>{};
  var statErrors = 0, linksSkipped = 0;
  for (var i = 0; i < roots.length; i++) {
    final files = <File>[];
    try {
      sourceDirectories[roots[i]] = await Directory(roots[i]).stat();
      await for (final entry in Directory(roots[i]).list(followLinks: false)) {
        if (entry is Link) {
          linksSkipped++;
          continue;
        }
        if (entry is File) files.add(entry);
        if (entry is Directory && path.basename(entry.path) == 'pendant_ring_custody') {
          sourceDirectories[entry.path] = await entry.stat();
          await for (final receipt in entry.list(followLinks: false)) {
            if (receipt is File) {
              files.add(receipt);
            } else {
              linksSkipped++;
            }
          }
        }
      }
    } catch (_) {
      directoryErrors.add(i);
    }
    // Stat in bounded parallel batches. Awaiting one stat at a time costs an
    // I/O-service round trip per file: with ~164k leaked audio files in
    // Documents that alone took ~40 s of the diagnostics export.
    for (var start = 0; start < files.length; start += _statConcurrency) {
      final batch = files.sublist(start, min(start + _statConcurrency, files.length));
      final stats = await Future.wait(batch.map((f) => f.stat().then<FileStat?>((s) => s, onError: (_) => null)));
      for (var j = 0; j < batch.length; j++) {
        final entry = batch[j], stat = stats[j];
        if (stat == null || stat.type != FileSystemEntityType.file) {
          statErrors++;
          continue;
        }
        final name = path.basename(entry.path);
        final kind = path.basename(path.dirname(entry.path)) == 'pendant_ring_custody' ? 'ring_custody' : _kind(name);
        final value = _Metadata(path.normalize(entry.path), kind ?? (_audio(name) ? 'audio' : 'other'), stat.size,
            stat.modified.microsecondsSinceEpoch, stat.changed.microsecondsSinceEpoch);
        // Stat all regular files so a referenced legacy name is not falsely
        // called missing merely because it predates today's audio prefix.
        audio[value.filePath] = value;
        if (kind != null) metadata.add(value);
      }
    }
  }
  final buckets = {for (final e in memoryBuckets.entries) e.key: List<RecordingInventoryRow>.of(e.value)};
  final indexFiles = <Map<String, Object?>>[], references = <String>{};
  final loaderEvents = <Map<String, Object?>>[];
  var unreadable = 0, changed = 0, invalidRows = 0;
  for (final meta in metadata) {
    final details = <String, Object?>{
      'kind': meta.kind,
      'bytes': meta.bytes,
      'modified_ms': meta.modifiedMs,
      'metadata_changed_ms': meta.changedMs
    };
    _Decoded result;
    try {
      // Bound one allocation; skipped/unreadable sources prevent certainty about orphans.
      if (meta.bytes > 128 * 1024 * 1024) {
        result = _Decoded([], 'size_limit');
      } else {
        final bytes = await File(meta.filePath).readAsBytes();
        final name = path.basename(meta.filePath);
        result = await offUiIsolate(() => _decode(bytes, meta.kind, name),
            size: bytes.length, threshold: 0, debugName: 'recording_inventory_decode');
        final after = await File(meta.filePath).stat();
        if (after.size != meta.bytes || after.modified.microsecondsSinceEpoch != meta.modifiedUs) changed++;
      }
    } catch (_) {
      result = _Decoded([], 'unreadable');
    }
    details['read_result'] = result.error ?? 'readable';
    if (result.error != null) unreadable++;
    details['rows'] = result.error == null ? result.rows.length : null;
    details['invalid_minimum_schema_rows'] = result.invalidRows;
    invalidRows += result.invalidRows;
    indexFiles.add(details);
    loaderEvents.addAll(result.loaderEvents);
    buckets.putIfAbsent(meta.kind, () => []).addAll(result.rows);
    if (meta.kind == 'capture_committed') {
      final expected = 'capture_committed_${sha256.convert(utf8.encode(currentOwner))}';
      final name = path.basename(meta.filePath).replaceFirst(RegExp(r'\.tmp$'), '');
      buckets[meta.kind]!.add(RecordingInventoryRow(
          status: 'unknown',
          captureSeconds: null,
          audioSeconds: null,
          indexBytes: 0,
          disk: false,
          owner: name == '$expected.json' || name == '$expected.jsonl' ? currentOwner : 'unknown-journal-owner'));
    }
  }
  final legacy = <RecordingInventoryRow>[
    for (final file in legacyFiles)
      RecordingInventoryRow(
          status: 'unknown',
          captureSeconds: _filenameTime(file),
          audioSeconds: null,
          indexBytes: 0,
          disk: true,
          filePath: file,
          rebase: false),
  ];
  buckets['legacy_preference_files'] = legacy;
  for (final item in [('legacy_jobs', legacyJobs), ('quarantined_legacy_jobs', corruptLegacyJobs)]) {
    if (item.$2.isEmpty) continue;
    final raw = item.$2;
    final decoded = await offUiIsolate(() {
      try {
        final value = jsonDecode(raw);
        return value is Map
            ? [
                for (final name in value.keys.whereType<String>())
                  RecordingInventoryRow(
                      status: 'unknown',
                      captureSeconds: _filenameTime(name),
                      audioSeconds: null,
                      indexBytes: 0,
                      disk: true,
                      filePath: name)
              ]
            : null;
      } catch (_) {
        return null;
      }
    }, size: raw.length, threshold: 0, debugName: 'recording_inventory_legacy');
    if (decoded == null) {
      unreadable++;
    } else {
      buckets[item.$1] = decoded;
    }
  }
  // All output below is constructed from counts, bounded vocabulary and times.
  // Paths, basenames, row IDs, account IDs and raw JSON never leave this function.
  final summary = await offUiIsolate(() {
    final summaries = <String, Object?>{};
    var unresolvedReferences = 0;
    const allowedBuckets = {
      'active',
      'retired',
      'foreign',
      'main_index',
      'backup_index',
      'temporary_index',
      'quarantine_index',
      'batch_journal',
      'ownership_receipts',
      'boot_journal',
      'legacy_preference_files',
      'legacy_jobs',
      'quarantined_legacy_jobs',
      'ring_custody',
      'capture_committed'
    };
    for (final entry in buckets.entries) {
      if (!allowedBuckets.contains(entry.key)) continue;
      final summary = _summarize(entry.value, phoneSeconds, currentOwner, documents, audio);
      final sources = indexFiles.where((f) => f['kind'] == entry.key);
      summary['readable_source_files'] = sources.where((f) => f['read_result'] == 'readable').length;
      summary['unreadable_source_files'] = sources.where((f) => f['read_result'] != 'readable').length;
      summaries[entry.key] = summary;
      unresolvedReferences += summary['rows_without_file_reference']! as int;
      if (entry.key == 'boot_journal' || entry.key == 'capture_committed') continue;
      for (final row in entry.value) {
        final ref = _reference(row, documents);
        if (ref != null) references.add(ref);
      }
    }
    loaderEvents.sort((a, b) => ((a['at_ms'] as int?) ?? 0).compareTo((b['at_ms'] as int?) ?? 0));
    final directories = <Map<String, Object?>>[];
    for (var i = 0; i < roots.length; i++) {
      final files =
          audio.values.where((m) => path.dirname(m.filePath) == roots[i] && _audio(path.basename(m.filePath))).toList();
      final orphans = files.where((m) => !references.contains(m.filePath)).toList();
      int? minimum(Iterable<int> values) => values.isEmpty ? null : values.reduce((a, b) => a < b ? a : b);
      int? maximum(Iterable<int> values) => values.isEmpty ? null : values.reduce((a, b) => a > b ? a : b);
      directories.add({
        'kind': i == 0 ? 'documents' : 'configured_native',
        'readable': !directoryErrors.contains(i),
        'regular_files_seen': audio.values.where((m) => path.dirname(m.filePath) == roots[i]).length,
        'audio_files': files.length,
        'audio_bytes': files.fold<int>(0, (n, m) => n + m.bytes),
        'working_audio_files': files.where((m) => m.filePath.endsWith('.part') || m.filePath.endsWith('.torn')).length,
        'referenced_audio_files': files.length - orphans.length,
        'unreferenced_audio_files': orphans.length,
        'unreferenced_audio_bytes': orphans.fold<int>(0, (n, m) => n + m.bytes),
        'oldest_unreferenced_modified_ms': minimum(orphans.map((m) => m.modifiedMs)),
        'newest_unreferenced_modified_ms': maximum(orphans.map((m) => m.modifiedMs)),
        'oldest_file_modified_ms': minimum(files.map((m) => m.modifiedMs)),
        'newest_file_modified_ms': maximum(files.map((m) => m.modifiedMs)),
        'oldest_creation_ms': null,
        'newest_creation_ms': null
      });
    }
    return <String, Object?>{
      'schema_version': 1,
      'started_at_ms': started,
      'completed_at_ms': DateTime.now().millisecondsSinceEpoch,
      'snapshot_consistency': 'best_effort_no_writer_lock',
      'memory_snapshot_available': memoryBuckets.containsKey('active'),
      'capture_time_reference_seconds': phoneSeconds,
      'capture_time_reference_plausible': phoneSeconds >= 1704067200 && phoneSeconds <= 0x7fffffff,
      'capture_time_future_tolerance_seconds': 86400,
      'buckets': summaries,
      'index_files': indexFiles,
      'directories': directories,
      'unreadable_metadata_files': unreadable,
      'invalid_minimum_schema_rows': invalidRows,
      'rows_without_file_reference': unresolvedReferences,
      'metadata_changed_during_read': changed,
      'file_stat_errors': statErrors,
      'symlinks_skipped': linksSkipped,
      'orphan_scope': 'unreferenced_by_readable_indexes_journals_preferences_and_memory_snapshot',
      'audio_file_scope': 'audio_prefix_bin_part_torn_and_wav',
      'local_only_history': buckets.values.expand((rows) => rows).any((r) => r.onDeviceOnly || r.holdForUser),
      'legacy_preferences_complete': legacyPreferencesComplete,
      'orphan_census_complete': legacyPreferencesComplete &&
          unreadable == 0 &&
          invalidRows == 0 &&
          unresolvedReferences == 0 &&
          changed == 0 &&
          statErrors == 0 &&
          linksSkipped == 0 &&
          directoryErrors.isEmpty,
      'missing_file_scope': 'not_observed_as_regular_file_in_scanned_directories',
      'unique_missing_file_references': references.where((ref) => !audio.containsKey(ref)).length,
      'creation_time_availability': 'not_recorded_in_wal_schema_or_portable_dart_filestat',
      'free_disk_bytes': freeBytes,
      'last_recorded_loader_or_recovery': loaderEvents.isEmpty ? null : loaderEvents.last,
      'recorded_loader_events':
          loaderEvents.length > 24 ? loaderEvents.sublist(loaderEvents.length - 24) : loaderEvents,
      'totals_note': 'bucket_rows_and_durations_can_overlap_backups_and_duplicate_audio'
    };
  },
      size: audio.length + buckets.values.fold<int>(0, (n, r) => n + r.length),
      threshold: 0,
      debugName: 'recording_inventory_summary');
  // Keep local identities separate from the aggregate export. Isolate closures
  // receive immutable snapshots, never the ledger or its capture queue.
  final allReferences = <String>{
    for (final entry in buckets.entries)
      if (entry.key != 'boot_journal' && entry.key != 'capture_committed')
        for (final row in entry.value)
          if (_reference(row, documents) case final ref?) ref,
  };
  // Historical preference/job references have no owner stamp; they must not
  // disappear from phone-wide ownership proof merely because they are legacy.
  final ownerBuckets = buckets.entries.where((e) => e.key != 'boot_journal');
  final singleOwner = currentOwner.isNotEmpty &&
      ownerBuckets.expand((e) => e.value).every((r) => r.owner == currentOwner) &&
      buckets.entries
          .where((e) => const {
                'active',
                'retired',
                'foreign',
                'main_index',
                'backup_index',
                'temporary_index',
                'quarantine_index'
              }.contains(e.key))
          .expand((e) => e.value)
          .any((r) => r.owner == currentOwner);
  final complete = summary['orphan_census_complete'] == true;
  // A reference that differs only in case (or directory alias) can name the same file on
  // case-insensitive storage. Reserve by case-folded basename so such a file is never an orphan.
  final referencedNames = {for (final r in allReferences) path.basename(r).toLowerCase()};
  final candidates = audio.values
      .where((m) =>
          _audio(path.basename(m.filePath)) &&
          !LiveWalReceipt.isManagedBasename(path.basename(m.filePath)) &&
          !allReferences.contains(m.filePath) &&
          !referencedNames.contains(path.basename(m.filePath).toLowerCase()))
      .toList();
  final classified = await offUiIsolate(
      () => _classifyOrphans(candidates, phoneSeconds, singleOwner && complete, frameCache),
      size: candidates.length,
      threshold: 0,
      debugName: 'orphan_audio_classifier');
  summary['orphan_classification'] = {
    ...orphanClassificationSummary(classified.files, phoneSeconds),
    'frame_files_read': classified.reads,
    'frame_cache_hits': classified.hits,
  };
  return RecordingOrphanCensus(summary, classified.files, sourceDirectories, metadata, currentOwner, classified.cache);
}

/// Aggregate-only diagnostics. Local paths/owners in the census never escape.
Future<Map<String, Object?>> captureRecordingInventory(
        {required String documents,
        required Map<String, List<RecordingInventoryRow>> memoryBuckets,
        required int phoneSeconds,
        String currentOwner = '',
        List<String> additionalDirectories = const [],
        List<String> legacyFiles = const [],
        String legacyJobs = '',
        String corruptLegacyJobs = '',
        bool legacyPreferencesComplete = true,
        OrphanAudioFrameCache frameCache = const OrphanAudioFrameCache.empty(),
        int? freeBytes}) async =>
    (await captureRecordingCensus(
            documents: documents,
            memoryBuckets: memoryBuckets,
            phoneSeconds: phoneSeconds,
            currentOwner: currentOwner,
            additionalDirectories: additionalDirectories,
            legacyFiles: legacyFiles,
            legacyJobs: legacyJobs,
            corruptLegacyJobs: corruptLegacyJobs,
            legacyPreferencesComplete: legacyPreferencesComplete,
            frameCache: frameCache,
            freeBytes: freeBytes))
        .summary;
