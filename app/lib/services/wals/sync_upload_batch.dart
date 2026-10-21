import 'dart:convert';
import 'dart:io';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';

/// One batch is one server-side sync job, and a job must finish inside the
/// backend's 600s stale guard (backend/database/sync_jobs.py). The job's cost
/// follows its audio, so the batch is bounded by audio seconds: the 300s that
/// five 60s chunks always carried. Pendant ring custody drains audio into
/// ~10s WALs, and a five-file limit then shrank every job to 50s, so the same
/// audio needed six times the jobs against the same rate limiter.
const _syncUploadBatchAudioSeconds = 5 * chunkSizeInSeconds;

/// A batch that claims a live-capture manifest sends every file in it to
/// `/v2/sync-capture-manifest`, whose request accepts at most 20 files
/// (`SyncCaptureManifestRequest.files`, published as `maxItems` in
/// docs/api-reference/app-client-openapi.json). A larger batch would pass the
/// whole-conversation claim check and then be refused by the server. With
/// this ceiling, a conversation too large for one batch never claims at all.
const syncUploadBatchMaxFiles = 20;

bool _batchHasRoom(int batchFiles, int batchSeconds, Wal next) =>
    batchFiles == 0 ||
    (batchFiles < syncUploadBatchMaxFiles && batchSeconds + next.seconds <= _syncUploadBatchAudioSeconds);

List<Wal> _takeWithinBudget(Iterable<Wal> wals) {
  final batch = <Wal>[];
  var seconds = 0;
  for (final wal in wals) {
    if (!_batchHasRoom(batch.length, seconds, wal)) break;
    batch.add(wal);
    seconds += wal.seconds;
  }
  return batch;
}

const _captureEvidenceHeaderMaxBytes = 4096;

final _captureClaimRootPattern = RegExp(
  r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$',
);
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

bool captureEvidenceWalClaimable(Wal wal) => _captureEvidenceClaim(wal, _walUploadFileName(wal)) != null;

final _syncTimestampTokenPattern = RegExp(r'_([0-9]+(?:\.[0-9]+)?)\.bin$');

bool isMobileStandardBatchWal(Wal wal) => _walUploadFileName(wal).startsWith('audio_omimobilebatch');

double _syncWalAudioStart(Wal wal) {
  if (captureEvidenceWalClaimable(wal) || isMobileStandardBatchWal(wal)) {
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
    final walEnd = captureEvidenceWalClaimable(wal) || isMobileStandardBatchWal(wal)
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
  if (wals.length != files.length || wals.isEmpty) {
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
            isMobileStandardBatchWal(wal) == isMobileStandardBatchWal(ordered.first) &&
            _walLocationBatchKey(wal) == locationKey,
      )
      .toList();
  if (_captureEvidenceClaim(group.first, _walUploadFileName(group.first)) == null) {
    return _takeWithinBudget(group.where((wal) => _captureEvidenceClaim(wal, _walUploadFileName(wal)) == null));
  }
  final batch = <Wal>[];
  final claims = <Map<String, dynamic>>[];
  final names = <String>{};
  var batchSeconds = 0;
  for (final wal in group) {
    if (!_batchHasRoom(batch.length, batchSeconds, wal)) break;
    final name = _walUploadFileName(wal);
    final claim = _captureEvidenceClaim(wal, name);
    if (claim == null) continue;
    if (names.contains(name)) break;
    if (_encodeCaptureEvidenceClaims([...claims, claim]) == null) break;
    claims.add(claim);
    names.add(name);
    batch.add(wal);
    batchSeconds += wal.seconds;
  }
  return batch;
}
