part of 'recording_inventory.dart';

_Decoded _decode(Uint8List bytes, String kind) {
  try {
    final decoded = jsonDecode(utf8.decode(bytes));
    if (kind == 'capture_committed') {
      return decoded is List ? _Decoded([], null) : _Decoded([], 'invalid_schema');
    }
    if (kind == 'ring_custody') {
      if (decoded is! Map) return _Decoded([], 'invalid_schema');
      final rows = <RecordingInventoryRow>[];
      void visit(Object? value) {
        if (value is List) {
          for (final child in value) {
            visit(child);
          }
        }
        if (value is Map) {
          if (value.containsKey('file')) {
            if (value['file'] is! String || value['owner'] is! String) {
              throw const FormatException('invalid ring ref');
            }
            rows.add(RecordingInventoryRow(
                status: 'unknown',
                captureSeconds: null,
                audioSeconds: null,
                indexBytes: 0,
                disk: true,
                filePath: value['file'] as String,
                owner: value['owner'] as String));
          }
          for (final child in value.values) {
            visit(child);
          }
        }
      }

      visit(decoded);
      return _Decoded(rows, null);
    }
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
  if (name.startsWith('capture_committed_')) return 'capture_committed';
  if (name == 'boot_stages.json') return 'boot_journal';
  return null;
}
