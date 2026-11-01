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

/// The upload grouping key shared by every WAL of one recording: conversation,
/// recording session, batch family and location — exactly the tuple
/// [nextSyncUploadBatch] groups a batch by. The drain's per-recording share
/// cap counts batches with this key.
String recordingGroupKey(Wal wal) =>
    '${wal.conversationId}|${wal.recordingSessionId}|${isMobileStandardBatchWal(wal)}|${_walLocationBatchKey(wal) ?? ''}';

/// Gap at which two id-less recordings on one device count as separate runs.
/// Chunks of one file are exactly contiguous; the chunker's floor division can
/// shave a second off a computed run boundary.
const _deviceRunGapToleranceSeconds = 5;

/// Per-WAL share-cap group keys for [wals]: WALs carrying a conversation or
/// recording-session identity keep [recordingGroupKey]. Id-less WALs — device
/// imports (StorageSync → persistDeviceChunk, and the legacy SD card path)
/// carry neither id, so their tuple key is the same null|null|false| for every
/// recording on every device — instead key by contiguous audio run on one
/// device, which is the recording boundary the cap means to count (#14688).
///
/// Pass the full WAL list, not the drain's candidates: uploaded members stay
/// listed, so a run's key (anchored at its first chunk) stays stable while the
/// run uploads, defers and re-enters later passes. A batch may still span a
/// run boundary — [nextSyncUploadBatch] merges id-less WALs up to its audio
/// budget — but it counts toward its first member's run, and a deferred run
/// never rides along while it waits: the drain drops deferred groups from the
/// candidate list until nothing else is pending, at which point they resume.
Map<Wal, String> recordingGroupKeys(List<Wal> wals) {
  final keys = <Wal, String>{};
  final byDevice = <String, List<Wal>>{};
  for (final wal in wals) {
    if (wal.conversationId != null || wal.recordingSessionId != null) {
      keys[wal] = recordingGroupKey(wal);
    } else {
      byDevice.putIfAbsent(wal.device, () => []).add(wal);
    }
  }
  for (final entry in byDevice.entries) {
    final run = entry.value..sort((a, b) => a.timerStart.compareTo(b.timerStart));
    var runStart = run.first.timerStart;
    var runEnd = run.first.timerStart + run.first.seconds;
    for (final wal in run) {
      if (wal.timerStart > runEnd + _deviceRunGapToleranceSeconds) {
        runStart = wal.timerStart;
        runEnd = wal.timerStart + wal.seconds;
      } else if (wal.timerStart + wal.seconds > runEnd) {
        runEnd = wal.timerStart + wal.seconds;
      }
      keys[wal] = 'device-run|${entry.key}|$runStart';
    }
  }
  return keys;
}

/// Batches one recording may consume before a drain with other recordings
/// waiting moves on to them (36 × 300s = 3h of audio). Oldest-first ordering
/// is kept for the 30-day backfill deadline, but a pathological recording
/// (hours of overnight noise) otherwise monopolizes every interrupted pass —
/// each restart re-enters it at the head — and the small recordings behind it
/// starve (#14688). A drain with nothing else pending keeps its full-pass
/// order, so a lone backlog is never throttled.
const maxBatchesPerRecordingPerDrain = 36;

/// How long a recording's spent share keeps counting across drain passes. A
/// rate-limit break ends a pass before the cap fires; with a pass-local
/// counter the oldest recording could spend 35 batches of every pass and
/// starve the rest without ever deferring (#14688). The window outlasts the
/// server's rate-limit cooldowns, and entries expire so a share measured
/// days ago stops deferring a backlog that is now alone.
const drainRecordingShareWindowSeconds = 24 * 3600;

/// Upload priority for a pending set: live capture first (newest first), then
/// the historical backlog oldest first.
///
/// Live capture keeps newest-first because only it can still claim a capture
/// manifest and reach its still-running conversation. Everything older is
/// racing a hard server deadline — `SYNC_BACKFILL_MAX_AGE_SECONDS` (30 days),
/// after which the upload is refused with `backfill_lookback_exceeded` and the
/// recording can never sync. A drain that is interrupted (rate-limit break,
/// cancelled run, app backgrounding) truncates from the tail, so ordering
/// history newest-first starved exactly the recordings with the least recovery
/// time left; oldest-first makes every interruption cost the newest audio,
/// which has the most slack, instead.
List<Wal> nextSyncUploadBatch(List<Wal> pending, int nowSeconds) {
  final indexed = [for (var i = 0; i < pending.length; i++) (pending[i], i)]..sort((a, b) {
      final aLive = isLiveCaptureWal(a.$1, nowSeconds);
      final bLive = isLiveCaptureWal(b.$1, nowSeconds);
      if (aLive != bLive) return aLive ? -1 : 1;
      final byStart = aLive ? b.$1.timerStart.compareTo(a.$1.timerStart) : a.$1.timerStart.compareTo(b.$1.timerStart);
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
