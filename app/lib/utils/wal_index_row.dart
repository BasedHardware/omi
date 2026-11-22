// Validates a row for restart admission and receipt retirement using one
// decoder. Retiring a receipt must not rely on a row the loader would reject.
import 'package:omi/services/wals/wal.dart';

String walIndexQuarantinePrefix(String indexPath) => '$indexPath.corrupt-';

Wal decodeWalIndexRow(Object? entry) {
  if (entry is! Map<String, dynamic>) throw const FormatException();
  // Old indices can omit new optional fields, but a WAL without its
  // identity or with a wrong scalar type must never enter sync admission.
  if (entry['timer_start'] is! int || entry['codec'] is! String) throw const FormatException();
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
  ]) {
    if (entry[key] != null && entry[key] is! String) throw const FormatException();
  }
  return Wal.fromJson(entry);
}
