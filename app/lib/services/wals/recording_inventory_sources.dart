// Read-only decoding of recording references and custody owner evidence. Never
// call repairing loaders or infer server receipt from these local sources.
part of 'recording_inventory.dart';

final _custodyProofLogName = RegExp(r'^capture_committed_([0-9a-f]{64})\.jsonl(?:\.tmp)?$');

_Decoded _decode(Uint8List bytes, String kind, String name) {
  try {
    final content = utf8.decode(bytes);
    final proof = kind == 'capture_committed' ? _custodyProofLogName.firstMatch(name) : null;
    if (proof != null) {
      return CaptureCommittedJournal.isReadableProofLog(content, proof.group(1)!)
          ? _Decoded([], null)
          : _Decoded([], 'invalid_schema');
    }
    final decoded = jsonDecode(content);
    if (kind == 'capture_committed') {
      const fields = {
        'type',
        'conversation_id',
        'capture_root',
        'source_start',
        'source_end',
        'channel',
        'clock_epoch',
        'recording_session_id'
      };
      bool invalid(Object? row) {
        if (row is! Map || row.keys.any((key) => !fields.contains(key))) return true;
        if (row['type'] != null && row['type'] != 'capture_committed') return true;
        return CaptureCommittedEvent.parse(Map<String, dynamic>.from(row)) is! CaptureCommittedEvent;
      }

      return decoded is List && !decoded.any(invalid) ? _Decoded([], null) : _Decoded([], 'invalid_schema');
    }
    if (kind == 'ring_custody') return _decodeRingReferences(decoded);
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
              for (final entry in decoded.entries)
                RecordingInventoryRow(
                    status: 'unknown',
                    captureSeconds: null,
                    audioSeconds: null,
                    indexBytes: 0,
                    disk: false,
                    filePath: _string(entry.key),
                    owner: _string(entry.value))
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
    ], null, invalidRows: rows.where((row) => !_validWalReferenceRow(row)).length);
  } catch (_) {
    return _Decoded([], 'unreadable');
  }
}

// Optional legacy storage defaults to mem, exactly as Wal.fromJson. Present
// unknown storage or path types cannot prove the absence of a file reference.
bool _validWalReferenceRow(Object? value) {
  if (value is! Map || value['timer_start'] is! int || value['codec'] is! String) return false;
  final storage = value['storage'], file = value['file_path'];
  if (storage != null && !const {'mem', 'disk', 'sdcard', 'flashPage'}.contains(storage)) return false;
  if (file != null && file is! String) return false;
  if (storage == 'disk' && (file is! String || file.isEmpty)) return false;
  return true;
}

String? _kind(String name) {
  if (name == 'wals.json') return 'main_index';
  if (name == 'wals_backup.json') return 'backup_index';
  if (name == 'wals.json.tmp' || name == 'wals_backup.json.tmp') return 'temporary_index';
  if (name.startsWith('wals.json.corrupt-') || name.startsWith('wals_backup.json.corrupt-')) return 'quarantine_index';
  if (name.endsWith('.batch-journal')) return 'batch_journal';
  if (name == 'omibatch_owners.json') return 'ownership_receipts';
  if (name.startsWith('capture_committed_')) return 'capture_committed';
  if (name == 'boot_stages.json') return 'boot_journal';
  return null;
}

// Snapshot raw custody inputs without invoking repairing preference getters.
// Unknown types or archived inputs make every consumer's census incomplete.
class RecordingInventoryPreferences {
  RecordingInventoryPreferences._(this._raw);
  final Map<String, Object?> _raw;
  static const keys = {
    'batchAudioDir',
    'flash_page_pending_uploads',
    'localRecordingJobs',
    'localRecordingJobsCorrupt'
  };
  static RecordingInventoryPreferences capture(Set<String> names, Object? Function(String) read) {
    final raw = <String, Object?>{};
    for (final name in names) {
      if (keys.contains(name)) {
        final value = read(name);
        raw[name] = value is List ? List<Object?>.unmodifiable(value) : value;
      } else if (keys.any((key) => name.startsWith('$key.corrupt-'))) {
        // Presence alone fences custody; no archived value needs to be read.
        raw[name] = true;
      }
    }
    return RecordingInventoryPreferences._(raw);
  }

  bool get complete =>
      !_raw.keys.any((k) => !keys.contains(k)) &&
      ['batchAudioDir', 'localRecordingJobs', 'localRecordingJobsCorrupt']
          .every((k) => _raw[k] == null || _raw[k] is String) &&
      (_raw['flash_page_pending_uploads'] == null ||
          (_raw['flash_page_pending_uploads'] is List &&
              (_raw['flash_page_pending_uploads'] as List).every((v) => v is String)));
  String _text(String key) => _raw[key] is String ? _raw[key] as String : '';
  List<String> get directories => _text('batchAudioDir').isEmpty ? [] : [_text('batchAudioDir')];
  List<String> get files => (_raw['flash_page_pending_uploads'] is List
      ? (_raw['flash_page_pending_uploads'] as List).whereType<String>().toList()
      : <String>[]);

  /// Conservative alias fence. Build once off UI, never scan a pending-file
  /// archive for each unlink on the capture queue. Names stay device-local.
  Future<Set<String>> fileReferenceNames() {
    final names = files;
    return offUiIsolate(() => names.map((name) => path.basename(name).toLowerCase()).toSet(),
        size: names.length, threshold: 0, debugName: 'orphan_reference_names');
  }

  String get jobs => _text('localRecordingJobs');
  String get corruptJobs => _text('localRecordingJobsCorrupt');
  bool matches(RecordingInventoryPreferences other) {
    if (!complete || !other.complete) return false;
    for (final key in keys) {
      final a = _raw[key], b = other._raw[key];
      if (a is List && b is List) {
        if (a.length != b.length) return false;
        for (var i = 0; i < a.length; i++) {
          if (a[i] != b[i]) return false;
        }
      } else if (a != b) {
        return false;
      }
    }
    return true;
  }
}

_Decoded _decodeRingReferences(Object? decoded) {
  final rows = <RecordingInventoryRow>[];
  Never invalid() => throw const FormatException('unsupported ring custody schema');
  void fields(Map value, Set<String> allowed) {
    if (value.keys.any((key) => !allowed.contains(key))) {
      invalid();
    }
  }

  void reference(Object? value, {bool chunk = false}) {
    if (value is! Map) {
      invalid();
    }
    final ref = value;
    fields(ref, {
      'file',
      'bytes',
      'frames',
      'owner',
      'sha256',
      'live_ring',
      'live_start',
      'live_end',
      'batch_session',
      'live_device',
      'download_ring',
      'download_start',
      'download_end',
      'download_device'
    });
    if (ref['file'] is! String ||
        (ref['file'] as String).isEmpty ||
        ref['bytes'] is! int ||
        ref['frames'] is! int ||
        (ref['bytes'] as int) < 0 ||
        (ref['frames'] as int) < 0) {
      invalid();
    }
    for (final key in ['owner', 'sha256', 'batch_session', 'live_device', 'download_device']) {
      if (ref[key] != null && ref[key] is! String) {
        invalid();
      }
    }
    for (final key in ['live_ring', 'live_start', 'live_end', 'download_ring', 'download_start', 'download_end']) {
      if (ref[key] != null && ref[key] is! int) {
        invalid();
      }
    }
    if (ref.containsKey('download_ring') &&
        (ref['download_ring'] is! int ||
            ref['download_start'] is! int ||
            ref['download_end'] is! int ||
            ref['download_device'] is! String)) {
      invalid();
    }
    if (chunk &&
        (ref['live_start'] is! int ||
            ref['live_end'] is! int ||
            (ref['live_start'] as int) < 0 ||
            (ref['live_end'] as int) <= (ref['live_start'] as int))) {
      invalid();
    }
    rows.add(RecordingInventoryRow(
        status: 'unknown',
        captureSeconds: null,
        audioSeconds: null,
        indexBytes: 0,
        disk: true,
        filePath: ref['file'] as String,
        owner: ref['owner'] as String?));
  }

  void range(Object? value, {bool live = false}) {
    if (value is! Map) {
      invalid();
    }
    final item = value;
    fields(item, {'start_seq', 'end_seq', 'wals', if (live) 'start_live', if (live) 'end_live'});
    if (item['start_seq'] is! int ||
        item['end_seq'] is! int ||
        item['wals'] is! List ||
        (item['start_seq'] as int) < 0 ||
        (item['end_seq'] as int) <= (item['start_seq'] as int)) {
      invalid();
    }
    if (live &&
        (item['start_live'] is! int ||
            item['end_live'] is! int ||
            (item['start_live'] as int) < 0 ||
            (item['end_live'] as int) <= (item['start_live'] as int))) {
      invalid();
    }
    for (final ref in item['wals'] as List) {
      reference(ref);
    }
  }

  if (decoded is! Map) {
    invalid();
  }
  final root = decoded;
  if (root.containsKey('ranges')) {
    fields(root, {'device', 'ring', 'ranges'});
    if (root['device'] is! String ||
        (root['device'] as String).isEmpty ||
        root['ring'] is! int ||
        root['ranges'] is! List) {
      invalid();
    }
    for (final item in root['ranges'] as List) {
      range(item);
    }
  } else {
    fields(root, {
      'version',
      'device_id',
      'ring_id',
      'durable_seq',
      'last_advanced_seq',
      'last_durable_mark',
      'last_durable_mark_live_index',
      'last_advanced_mark',
      'live_ranges',
      'ring_ranges',
      'batch_sessions',
      'reported_read_seq',
      'reported_write_seq'
    });
    if (root['version'] is! int ||
        root['version'] != 1 ||
        root['device_id'] is! String ||
        (root['device_id'] as String).isEmpty ||
        root['live_ranges'] is! List ||
        root['ring_ranges'] is! List) {
      invalid();
    }
    for (final key in [
      'ring_id',
      'durable_seq',
      'last_advanced_seq',
      'last_durable_mark',
      'last_durable_mark_live_index',
      'last_advanced_mark',
      'reported_read_seq',
      'reported_write_seq'
    ]) {
      if (root[key] != null && root[key] is! int) {
        invalid();
      }
    }
    for (final item in root['live_ranges'] as List) {
      range(item, live: true);
    }
    for (final item in root['ring_ranges'] as List) {
      range(item);
    }
    if (root.containsKey('batch_sessions')) {
      if (root['batch_sessions'] is! List) {
        invalid();
      }
      for (final raw in root['batch_sessions'] as List) {
        if (raw is! Map) {
          invalid();
        }
        final session = raw;
        fields(session, {'id', 'marks', 'chunks'});
        if (session['id'] is! String ||
            (session['id'] as String).isEmpty ||
            session['marks'] is! List ||
            session['chunks'] is! List ||
            (session['marks'] as List).length > 4096 ||
            (session['chunks'] as List).length > 4096) {
          invalid();
        }
        var previousSeq = -1, previousOrdinal = -1;
        for (final mark in session['marks'] as List) {
          if (mark is! List || mark.length != 3 || mark.any((v) => v is! int)) {
            invalid();
          }
          final values = mark;
          final seq = values[0] as int, live = values[1] as int, ordinal = values[2] as int;
          if (seq <= previousSeq || ordinal <= previousOrdinal || live < 0 || live > 0xffff) {
            invalid();
          }
          previousSeq = seq;
          previousOrdinal = ordinal;
        }
        for (final ref in session['chunks'] as List) {
          reference(ref, chunk: true);
        }
      }
    }
  }
  return _Decoded(rows, null);
}
