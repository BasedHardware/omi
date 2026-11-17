import 'dart:convert';
import 'dart:io';
import 'dart:math' show min;
import 'dart:typed_data';

import 'package:path/path.dart' as path;
import 'package:omi/utils/off_ui_isolate.dart';

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
      this.rebase = true});
  final String status;
  final int? captureSeconds;
  final double? audioSeconds;
  final int indexBytes;
  final bool disk;
  final String? filePath;
  final String? owner;
  final bool rebase;
}

/// Concurrent stats per batch while walking a recordings directory.
const _statConcurrency = 64;

class _Metadata {
  _Metadata(this.filePath, this.kind, this.bytes, this.modifiedMs, this.changedMs);
  final String filePath, kind;
  final int bytes, modifiedMs, changedMs;
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
  final token = RegExp(r'_(-?\d+(?:\.\d+)?)\.bin(?:\.part|\.torn)?$').firstMatch(path.basename(name))?.group(1);
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
      owner: _string(row['owner_uid']));
}

_Decoded _decode(Uint8List bytes, String kind) {
  try {
    final decoded = jsonDecode(utf8.decode(bytes));
    if (kind == 'boot_journal') {
      if (decoded is! List) return _Decoded([], 'invalid_schema');
      final events = <Map<String, Object?>>[];
      for (final row in decoded.whereType<Map>()) {
        final stage = _string(row['stage']) ?? '';
        final state = row['state'];
        if ((stage.startsWith('quarantine:') || stage.contains('wal') || stage.contains('recover')) &&
            const {'begin', 'completed', 'failed', 'invalid_entry', 'invalid_schema', 'unreadable', 'rename_failed'}
                .contains(state)) {
          events.add({
            'category': stage.startsWith('quarantine:') ? 'index_quarantine' : 'loader_or_recovery',
            'result': state,
            'at_ms': _integer(row['at_ms'])
          });
        }
      }
      return _Decoded([], null, loaderEvents: events.length > 24 ? events.sublist(events.length - 24) : events);
    }
    if (kind == 'ownership_receipts') {
      return decoded is Map
          ? _Decoded([
              for (final owner in decoded.values)
                RecordingInventoryRow(
                    status: 'unknown',
                    captureSeconds: null,
                    audioSeconds: null,
                    indexBytes: 0,
                    disk: false,
                    owner: _string(owner))
            ], null)
          : _Decoded([], 'invalid_schema');
    }
    final List rows;
    if (kind == 'batch_journal') {
      if (decoded is! Map) return _Decoded([], 'invalid_schema');
      rows = [decoded];
    } else {
      if (decoded is! Map || decoded['wals'] is! List) return _Decoded([], 'invalid_schema');
      rows = decoded['wals'] as List;
    }
    return _Decoded([
      for (final row in rows)
        row is Map
            ? _row(row)
            : const RecordingInventoryRow(
                status: 'unknown', captureSeconds: null, audioSeconds: null, indexBytes: 0, disk: false)
    ], null,
        invalidRows: rows.where((row) => row is! Map || row['timer_start'] is! int || row['codec'] is! String).length);
  } catch (_) {
    return _Decoded([], 'unreadable');
  }
}

String? _kind(String name) {
  if (name == 'wals.json') return 'main_index';
  if (name == 'wals_backup.json') return 'backup_index';
  if (name == 'wals.json.tmp' || name == 'wals_backup.json.tmp') return 'temporary_index';
  if (name.startsWith('wals.json.corrupt-') || name.startsWith('wals_backup.json.corrupt-')) return 'quarantine_index';
  if (name.endsWith('.batch-journal')) return 'batch_journal';
  if (name == 'omibatch_owners.json') return 'ownership_receipts';
  if (name == 'boot_stages.json') return 'boot_journal';
  return null;
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
Future<Map<String, Object?>> captureRecordingInventory(
    {required String documents,
    required Map<String, List<RecordingInventoryRow>> memoryBuckets,
    required int phoneSeconds,
    String currentOwner = '',
    List<String> additionalDirectories = const [],
    List<String> legacyFiles = const [],
    String legacyJobs = '',
    String corruptLegacyJobs = '',
    int? freeBytes}) async {
  final started = DateTime.now().millisecondsSinceEpoch;
  final roots =
      {path.normalize(documents), ...additionalDirectories.where((p) => p.isNotEmpty).map(path.normalize)}.toList();
  final audio = <String, _Metadata>{}, metadata = <_Metadata>[];
  final directoryErrors = <int>[];
  var statErrors = 0, linksSkipped = 0;
  for (var i = 0; i < roots.length; i++) {
    final files = <File>[];
    try {
      await for (final entry in Directory(roots[i]).list(followLinks: false)) {
        if (entry is Link) {
          linksSkipped++;
          continue;
        }
        if (entry is File) files.add(entry);
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
        final name = path.basename(entry.path), kind = _kind(name);
        final value = _Metadata(path.normalize(entry.path), kind ?? (_audio(name) ? 'audio' : 'other'), stat.size,
            stat.modified.millisecondsSinceEpoch, stat.changed.millisecondsSinceEpoch);
        // Stat all regular files so a referenced legacy name is not falsely
        // called missing merely because it predates today's audio prefix.
        audio[value.filePath] = value;
        if (kind != null) metadata.add(value);
      }
    }
  }
  final buckets = Map<String, List<RecordingInventoryRow>>.of(memoryBuckets);
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
        result = await offUiIsolate(() => _decode(bytes, meta.kind),
            size: bytes.length, threshold: 0, debugName: 'recording_inventory_decode');
        final after = await File(meta.filePath).stat();
        if (after.size != meta.bytes || after.modified.millisecondsSinceEpoch != meta.modifiedMs) changed++;
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
  return offUiIsolate(() {
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
      'quarantined_legacy_jobs'
    };
    for (final entry in buckets.entries) {
      if (!allowedBuckets.contains(entry.key)) continue;
      final summary = _summarize(entry.value, phoneSeconds, currentOwner, documents, audio);
      final sources = indexFiles.where((f) => f['kind'] == entry.key);
      summary['readable_source_files'] = sources.where((f) => f['read_result'] == 'readable').length;
      summary['unreadable_source_files'] = sources.where((f) => f['read_result'] != 'readable').length;
      summaries[entry.key] = summary;
      unresolvedReferences += summary['rows_without_file_reference']! as int;
      if (entry.key == 'ownership_receipts' || entry.key == 'boot_journal') continue;
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
        'working_audio_files': files.where((m) => m.filePath.endsWith('.part')).length,
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
      'orphan_census_complete': unreadable == 0 &&
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
}
