import 'dart:convert';

import 'package:omi/services/wals/wal.dart';

/// Owns the on-disk row schema for readers and both backup writers. A JSON
/// document that would lose rows on admission cannot replace a good backup.
/// The visitor validates one Wal at a time without retaining a second history.
bool visitWalIndex(String content, void Function(int, Wal) onRow) {
  final decoded = jsonDecode(content);
  if (decoded is! Map<String, dynamic> || decoded['wals'] is! List) {
    throw const FormatException('invalid_schema');
  }
  final entries = decoded['wals'] as List;
  var invalid = false;
  for (var i = 0; i < entries.length; i++) {
    final entry = entries[i];
    try {
      if (entry is! Map<String, dynamic>) throw const FormatException();
      // Old indices can omit new optional fields, but a WAL without its
      // identity or with a wrong scalar type must never enter sync admission.
      if (entry['timer_start'] is! int || entry['codec'] is! String) throw const FormatException();
      // A file-backed row must not fall through from an unknown/missing
      // storage enum to mem: the next flush would replace its reference
      // with a newly named empty file. Retire the raw row in quarantine.
      final storage = WalStorage.values.asNameMap()[entry['storage']];
      if (entry['storage'] != null && storage == null ||
          entry['file_path'] is String &&
              (entry['file_path'] as String).isNotEmpty &&
              (storage == null || storage == WalStorage.mem)) {
        throw const FormatException();
      }
      for (final key in [
        'channel',
        'sample_rate',
        'seconds',
        'storage_offset',
        'storage_total_bytes',
        'file_num',
        'total_frames',
        'synced_frame_offset',
        'retry_count',
        'last_retry_at',
        'uploaded_at',
        'source_frame_start',
        'source_clock_epoch',
        'live_ring_id',
        'live_ordinal_start',
        'live_ordinal_end',
        'download_ring_id',
        'download_seq_start',
        'download_seq_end',
        'download_file_bytes',
      ]) {
        if (entry[key] != null && entry[key] is! int) throw const FormatException();
      }
      for (final key in [
        'file_path',
        'device',
        'device_model',
        'conversation_id',
        'recording_session_id',
        'owner_uid',
        'capture_root',
        'job_id',
        'batch_live_session',
        'live_device_id',
        'file_write_id',
      ]) {
        if (entry[key] != null && entry[key] is! String) throw const FormatException();
      }
      onRow(i, Wal.fromJson(entry));
    } catch (_) {
      invalid = true;
    }
  }
  return invalid;
}

({List<Wal> wals, bool invalid}) decodeWalIndex(String content, String path) {
  final loaded = <Wal>[];
  final invalid = visitWalIndex(content, (_, wal) => loaded.add(wal));
  if (!invalid) {
    for (var i = 0; i < loaded.length; i++) {
      loaded[i].loadedIndexToken = i;
      loaded[i].loadedIndexSource = path;
    }
  }
  return (wals: loaded, invalid: invalid);
}
