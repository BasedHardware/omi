import 'dart:convert';
import 'dart:io';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';

/// One batch is one server-side sync job, and a job must finish inside the
/// backend's 600s stale guard (backend/database/sync_jobs.py).
const _syncUploadBatchLimit = 5;

const _captureEvidenceV1DarkWrite = bool.fromEnvironment('CAPTURE_EVIDENCE_V1_DARK_WRITE');

const _captureEvidenceHeaderMaxBytes = 4096;

final _captureClaimRootPattern =
    RegExp(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$');
final _captureClaimNamePattern = RegExp(r'^[A-Za-z0-9_.\-]{1,255}$');

String _walUploadFileName(Wal wal) =>
    (wal.filePath != null && wal.filePath!.isNotEmpty) ? wal.filePath!.split('/').last : wal.getFileName();

Map<String, dynamic>? _captureEvidenceClaim(Wal wal, String name) {
  final root = wal.captureRoot;
  final start = wal.sourceFrameStart;
  final epoch = wal.sourceClockEpoch;
  if (root == null ||
      !_captureClaimRootPattern.hasMatch(root) ||
      start == null ||
      start < 0 ||
      epoch == null ||
      epoch < 0 ||
      wal.totalFrames <= 0 ||
      wal.sampleRate <= 0 ||
      wal.channel != 1 ||
      (!wal.codec.isOpusSupported() && wal.codec != BleAudioCodec.pcm16) ||
      !_captureClaimNamePattern.hasMatch(name)) {
    return null;
  }
  return {
    'name': name,
    'capture_root': root,
    'clock_epoch': epoch,
    'source_frame_start': start,
    'frame_count': wal.totalFrames,
    'rate_hz': wal.sampleRate,
    'codec': wal.codec == BleAudioCodec.pcm16 ? 'pcm16' : 'opus',
    'channel': 'mono',
  };
}

bool captureEvidenceWalClaimable(Wal wal) =>
    _captureEvidenceV1DarkWrite && _captureEvidenceClaim(wal, _walUploadFileName(wal)) != null;

final _syncTimestampTokenPattern = RegExp(r'_([0-9]+(?:\.[0-9]+)?)\.bin$');

double _syncWalAudioStart(Wal wal) {
  if (captureEvidenceWalClaimable(wal)) {
    final match = _syncTimestampTokenPattern.firstMatch(_walUploadFileName(wal));
    final parsed = match == null ? null : double.tryParse(match.group(1)!);
    if (parsed != null && parsed.isFinite) return parsed;
  }
  return wal.timerStart.toDouble();
}

({double start, double end}) syncUploadAudioBounds(List<Wal> wals) {
  assert(wals.isNotEmpty);
  var start = double.infinity;
  var end = double.negativeInfinity;
  for (final wal in wals) {
    final walStart = _syncWalAudioStart(wal);
    final walEnd = captureEvidenceWalClaimable(wal)
        ? walStart + wal.totalFrames / wal.codec.getFramesPerSecond()
        : (wal.timerStart + wal.seconds).toDouble();
    if (walStart < start) start = walStart;
    if (walEnd > end) end = walEnd;
  }
  return (start: start, end: end);
}

String? _encodeCaptureEvidenceClaims(List<Map<String, dynamic>> claims) {
  final encoded = jsonEncode({'version': 1, 'files': claims});
  return utf8.encode(encoded).length <= _captureEvidenceHeaderMaxBytes ? encoded : null;
}

/// Optional S1 file-position claim. The upload remains valid when a legacy or
/// mixed batch cannot make a single bounded claim; the server then records
/// unknown coverage instead of inventing positions from timestamps.
String? captureEvidenceUploadHeader(List<Wal> wals, List<File> files) {
  if (!_captureEvidenceV1DarkWrite || wals.length != files.length || wals.isEmpty) {
    return null;
  }
  final claims = <Map<String, dynamic>>[];
  for (var i = 0; i < wals.length; i++) {
    final claim = _captureEvidenceClaim(wals[i], files[i].uri.pathSegments.last);
    if (claim == null) return null;
    claims.add(claim);
  }
  return _encodeCaptureEvidenceClaims(claims);
}

String? _walLocationBatchKey(Wal wal) {
  final geolocation = wal.geolocation;
  if (geolocation == null) return null;
  return '${geolocation.time?.toUtc().toIso8601String()}|${geolocation.latitude}|${geolocation.longitude}';
}

List<Wal> nextSyncUploadBatch(List<Wal> pending, int nowSeconds) {
  if (!_captureEvidenceV1DarkWrite) {
    final ordered = List<Wal>.from(pending)..sort((a, b) => b.timerStart.compareTo(a.timerStart));
    if (ordered.isEmpty) return const [];
    final conversationId = ordered.first.conversationId;
    final recordingSessionId = ordered.first.recordingSessionId;
    final locationKey = _walLocationBatchKey(ordered.first);
    return ordered
        .where(
          (wal) =>
              wal.conversationId == conversationId &&
              wal.recordingSessionId == recordingSessionId &&
              _walLocationBatchKey(wal) == locationKey,
        )
        .take(_syncUploadBatchLimit)
        .toList();
  }
  final indexed = [for (var i = 0; i < pending.length; i++) (pending[i], i)]..sort((a, b) {
      final byStart = b.$1.timerStart.compareTo(a.$1.timerStart);
      return byStart != 0 ? byStart : a.$2.compareTo(b.$2);
    });
  if (indexed.isEmpty) return const [];
  final ordered = [for (final entry in indexed) entry.$1];
  final conversationId = ordered.first.conversationId;
  final recordingSessionId = ordered.first.recordingSessionId;
  final locationKey = _walLocationBatchKey(ordered.first);
  final group = ordered
      .where(
        (wal) =>
            wal.conversationId == conversationId &&
            wal.recordingSessionId == recordingSessionId &&
            _walLocationBatchKey(wal) == locationKey,
      )
      .toList();
  if (_captureEvidenceClaim(group.first, _walUploadFileName(group.first)) == null) {
    return group
        .where((wal) => _captureEvidenceClaim(wal, _walUploadFileName(wal)) == null)
        .take(_syncUploadBatchLimit)
        .toList();
  }
  final batch = <Wal>[];
  final claims = <Map<String, dynamic>>[];
  final names = <String>{};
  for (final wal in group) {
    if (batch.length >= _syncUploadBatchLimit) break;
    final name = _walUploadFileName(wal);
    final claim = _captureEvidenceClaim(wal, name);
    if (claim == null) continue;
    if (names.contains(name)) break;
    if (_encodeCaptureEvidenceClaims([...claims, claim]) == null) break;
    claims.add(claim);
    names.add(name);
    batch.add(wal);
  }
  return batch;
}
