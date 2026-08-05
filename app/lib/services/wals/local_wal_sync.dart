import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/conversation_audio_assembler.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/mutex.dart';
import 'package:omi/utils/wal_file_manager.dart';

/// Error string the backend's stale guard sets when a job sits queued past
/// STALE_THRESHOLD_SECONDS without ever reaching a worker. See backend issue
/// #7469 — if this string changes, update here and keep the structural check
/// below ('failed' with totalSegments==0) as the durable signal.
const _kBackendBusyErrorHint = 'background worker likely died';
const _freshSyncCutoffSeconds = 6 * 60 * 60;
const _defaultConversationBoundarySeconds = 2 * 60;
const _captureUploadWalLimit = 2000;

/// Legacy/historical files per upload batch. A conversation-bound capture uses
/// [_captureUploadWalLimit] so its immutable recovery units remain one server
/// transaction instead of racing as many independent jobs.
const _syncUploadBatchLimit = 20;

typedef WalPersister = Future<bool> Function(List<Wal> wals);
typedef WalPathResolver = Future<String?> Function(String? pathOrName);
typedef SyncJobStatusFetcher = Future<SyncJobFetch> Function(String jobId);
typedef ConversationBoundarySecondsProvider = int Function();

class AuthorizedRecoverySyncResult {
  const AuthorizedRecoverySyncResult({
    required this.response,
    required this.hasDeferredRecovery,
  });

  final SyncLocalFilesResponse? response;

  /// Retryable raw/archive work inside the receipt still exists locally.
  ///
  /// A recent range remains deferred until the configured conversation close;
  /// a failed upload remains deferred until a later retry. Newer and unrelated
  /// backfill is deliberately outside this result.
  final bool hasDeferredRecovery;
}

class _AuthorizedRecoveryScope {
  const _AuthorizedRecoveryScope({
    required this.deviceId,
    required this.targetWriteSeq,
  });

  final String deviceId;
  final int targetWriteSeq;
}

enum SyncJobTerminalPolicy { wait, acknowledge, retry }

/// The shared WAL acknowledgement boundary for async sync jobs.
///
/// Only the backend's truthful `completed` state permits local audio to become
/// terminally synced. Partial and full failures deliberately take the retry
/// path so the retained WAL remains recoverable.
@visibleForTesting
SyncJobTerminalPolicy syncJobTerminalPolicy({
  required String status,
  required bool isTerminal,
}) {
  if (!isTerminal) return SyncJobTerminalPolicy.wait;
  return status == 'completed' ? SyncJobTerminalPolicy.acknowledge : SyncJobTerminalPolicy.retry;
}

@visibleForTesting
bool syncJobIsBackendBusy(SyncJobStatusResponse status) {
  if ((status.error ?? '').contains(_kBackendBusyErrorHint)) return true;
  // Legacy stale-worker failures predate reason_code. New typed failures with
  // totalSegments=0 carry a reason and must consume retry budget normally.
  final reasonCode = status.reasonCode;
  return status.status == 'failed' && status.totalSegments == 0 && (reasonCode == null || reasonCode.isEmpty);
}

SyncUploadLane syncUploadLaneForTimestamp(
  int captureSeconds,
  int nowSeconds, {
  required bool hasServerCaptureProof,
}) =>
    hasServerCaptureProof && nowSeconds - captureSeconds <= _freshSyncCutoffSeconds
        ? SyncUploadLane.fresh
        : SyncUploadLane.backfill;

SyncUploadLane _syncLaneForWal(Wal wal, int nowSeconds) => syncUploadLaneForTimestamp(
      wal.timerStart,
      nowSeconds,
      hasServerCaptureProof: wal.conversationId != null || wal.uploadIntent == WalUploadIntent.liveContinuity,
    );

bool isLiveCaptureWal(Wal wal, int nowSeconds) =>
    wal.conversationId != null &&
    _syncLaneForWal(wal, nowSeconds) == SyncUploadLane.fresh &&
    nowSeconds - wal.timerStart <= _freshSyncCutoffSeconds;

/// The server capture manifest is immutable for one conversation. Claim it
/// only when this upload owns every currently pending WAL for that owner;
/// claiming a partial batch would permanently strand the siblings.
@visibleForTesting
bool canClaimLiveCapture(
  List<Wal> batch,
  List<Wal> pendingForConversation,
  int nowSeconds,
) =>
    batch.isNotEmpty && isLiveCaptureWal(batch.first, nowSeconds) && pendingForConversation.length <= batch.length;

bool _isUnboundStorageContinuity(Wal wal) =>
    wal.uploadIntent == WalUploadIntent.liveContinuity &&
    wal.originalStorage == WalStorage.sdcard &&
    wal.conversationId == null;

double _walEndSeconds(Wal wal) => wal.wallClockEndSeconds;

bool _isRawRingFragment(Wal wal) => wal.originalStorage == WalStorage.sdcard && _ringSourceRange(wal) != null;

bool _isRingRecoveryArtifact(Wal wal) =>
    wal.originalStorage == WalStorage.sdcard && RingProtocol.parseRecoverySourceRange(wal.sourceId) != null;

bool _isDurableRingCoverageArtifact(Wal wal) =>
    wal.originalStorage == WalStorage.sdcard && RingProtocol.parseDurableCoverageSourceRange(wal.sourceId) != null;

bool _isLegacyRingArchive(Wal wal) =>
    _isRingRecoveryArtifact(wal) &&
    !_isDurableRingCoverageArtifact(wal) &&
    wal.sourceId?.startsWith('archive_ring_') == true;

bool _isUnassembledConversationRepair(Wal wal) => wal.conversationId != null && _isRingRecoveryArtifact(wal);

bool _sameRingEncoding(Wal left, Wal right) =>
    left.device == right.device &&
    left.codec == right.codec &&
    left.sampleRate == right.sampleRate &&
    left.channel == right.channel &&
    left.frameSize == right.frameSize;

String _ringEncodingBucket(Wal wal) => [
      wal.device,
      wal.codec.name,
      wal.sampleRate,
      wal.channel,
      wal.frameSize,
    ].join('|');

List<List<Wal>> _continuousRingRecoveryGroups(
  Iterable<Wal> wals, {
  required int conversationBoundarySeconds,
  int? maxWallSeconds,
  bool requireContiguousSequence = false,
  int? sequenceBoundary,
}) {
  final buckets = <String, List<Wal>>{};
  for (final wal in wals) {
    buckets.putIfAbsent(_ringEncodingBucket(wal), () => []).add(wal);
  }

  final groups = <List<Wal>>[];
  for (final bucket in buckets.values) {
    bucket.sort((left, right) {
      final leftRange = RingProtocol.parseRecoverySourceRange(left.sourceId);
      final rightRange = RingProtocol.parseRecoverySourceRange(right.sourceId);
      final sequenceCompare = (leftRange?.start ?? 0).compareTo(rightRange?.start ?? 0);
      if (sequenceCompare != 0) return sequenceCompare;
      final timeCompare = left.timerStart.compareTo(right.timerStart);
      if (timeCompare != 0) return timeCompare;
      return left.id.compareTo(right.id);
    });

    for (final wal in bucket) {
      if (groups.isEmpty || !_sameRingEncoding(groups.last.last, wal)) {
        groups.add([wal]);
        continue;
      }
      final group = groups.last;
      final wallGap = wal.timerStart - _walEndSeconds(group.last);
      final wallSpan = _walEndSeconds(wal) - group.first.timerStart;
      final sequenceJoins = !requireContiguousSequence || _sequenceRangeTouchesGroup(group, wal);
      final boundaryJoins = sequenceBoundary == null || _sameSequenceBoundarySide(group, wal, sequenceBoundary);
      if (wallGap < conversationBoundarySeconds &&
          (maxWallSeconds == null || wallSpan <= maxWallSeconds) &&
          sequenceJoins &&
          boundaryJoins) {
        group.add(wal);
      } else {
        groups.add([wal]);
      }
    }
  }
  return groups;
}

int _sequenceBoundarySide(Wal wal, int boundary) {
  final range = RingProtocol.parseRecoverySourceRange(wal.sourceId);
  if (range == null || (range.start < boundary && range.end > boundary)) {
    return 0;
  }
  return range.end <= boundary ? -1 : 1;
}

bool _sameSequenceBoundarySide(List<Wal> group, Wal candidate, int boundary) {
  final candidateSide = _sequenceBoundarySide(candidate, boundary);
  if (candidateSide == 0) return false;
  return group.every((wal) => _sequenceBoundarySide(wal, boundary) == candidateSide);
}

bool _sequenceRangeTouchesGroup(List<Wal> group, Wal candidate) {
  final candidateRange = RingProtocol.parseRecoverySourceRange(candidate.sourceId);
  if (candidateRange == null) return false;
  final firstRange = RingProtocol.parseRecoverySourceRange(group.first.sourceId);
  if (firstRange == null) return false;
  var groupStart = firstRange.start;
  var groupEnd = firstRange.end;
  for (final wal in group.skip(1)) {
    final range = RingProtocol.parseRecoverySourceRange(wal.sourceId);
    if (range == null) return false;
    if (range.start < groupStart) groupStart = range.start;
    if (range.end > groupEnd) groupEnd = range.end;
  }
  return candidateRange.start <= groupEnd && candidateRange.end >= groupStart;
}

List<({int start, int end})> _orderedRecoveryRanges(List<Wal> wals) {
  final ranges = wals
      .map((wal) => RingProtocol.parseRecoverySourceRange(wal.sourceId))
      .whereType<({int start, int end})>()
      .toList()
    ..sort((left, right) {
      final startCompare = left.start.compareTo(right.start);
      return startCompare != 0 ? startCompare : left.end.compareTo(right.end);
    });
  return ranges;
}

bool _hasNonOverlappingRecoverySequence(List<Wal> group) {
  final ranges = _orderedRecoveryRanges(group);
  if (ranges.length != group.length) return false;
  for (var index = 1; index < ranges.length; index++) {
    if (ranges[index].start < ranges[index - 1].end) return false;
  }
  return true;
}

Set<Wal>? _exactRecoveryUploadTile(List<Wal> group) {
  final ranges = <Wal, ({int start, int end})>{};
  for (final wal in group) {
    final range = RingProtocol.parseRecoverySourceRange(wal.sourceId);
    if (range == null || range.end <= range.start) return null;
    ranges[wal] = range;
  }
  if (ranges.isEmpty) return <Wal>{};

  final start = ranges.values.map((range) => range.start).reduce(min);
  final end = ranges.values.map((range) => range.end).reduce(max);
  final byStart = <int, List<Wal>>{};
  for (final entry in ranges.entries) {
    byStart.putIfAbsent(entry.value.start, () => []).add(entry.key);
  }
  for (final candidates in byStart.values) {
    candidates.sort((left, right) {
      final durableCompare = (_isLegacyRingArchive(left) ? 1 : 0).compareTo(_isLegacyRingArchive(right) ? 1 : 0);
      if (durableCompare != 0) return durableCompare;
      final endCompare = ranges[right]!.end.compareTo(ranges[left]!.end);
      return endCompare != 0 ? endCompare : left.id.compareTo(right.id);
    });
  }

  final best = <int, ({List<Wal> wals, int legacyCount})>{
    start: (wals: const <Wal>[], legacyCount: 0),
  };
  final points = ranges.values.expand((range) => [range.start, range.end]).toSet().toList()..sort();
  for (final point in points) {
    final prefix = best[point];
    if (prefix == null) continue;
    for (final candidate in byStart[point] ?? const <Wal>[]) {
      final candidateEnd = ranges[candidate]!.end;
      final next = (
        wals: [...prefix.wals, candidate],
        legacyCount: prefix.legacyCount + (_isLegacyRingArchive(candidate) ? 1 : 0),
      );
      final current = best[candidateEnd];
      if (current == null ||
          next.legacyCount < current.legacyCount ||
          (next.legacyCount == current.legacyCount && next.wals.length < current.wals.length)) {
        best[candidateEnd] = next;
      }
    }
  }
  return best[end]?.wals.toSet();
}

List<List<Wal>> _recoverySequenceComponents(List<Wal> group) {
  final ordered = List<Wal>.from(group)
    ..sort((left, right) {
      final leftRange = RingProtocol.parseRecoverySourceRange(left.sourceId)!;
      final rightRange = RingProtocol.parseRecoverySourceRange(right.sourceId)!;
      final startCompare = leftRange.start.compareTo(rightRange.start);
      return startCompare != 0 ? startCompare : leftRange.end.compareTo(rightRange.end);
    });
  final components = <List<Wal>>[];
  var componentEnd = -1;
  for (final wal in ordered) {
    final range = RingProtocol.parseRecoverySourceRange(wal.sourceId)!;
    if (components.isEmpty || range.start > componentEnd) {
      components.add([wal]);
      componentEnd = range.end;
      continue;
    }
    components.last.add(wal);
    if (range.end > componentEnd) componentEnd = range.end;
  }
  return components;
}

Set<Wal> _blockedUnassembledRecoveryArtifacts(
  List<Wal> pending, {
  required int conversationBoundarySeconds,
}) {
  final blocked = Set<Wal>.identity();
  final recoveryGroups = _continuousRingRecoveryGroups(
    pending.where(
      (wal) => wal.conversationId == null && _isRingRecoveryArtifact(wal),
    ),
    conversationBoundarySeconds: conversationBoundarySeconds,
  );
  for (final group in recoveryGroups) {
    for (final component in _recoverySequenceComponents(group)) {
      // A raw sibling means compaction has not yet committed this exact
      // sequence component. Independent components in the same wall-time
      // conversation remain eligible.
      if (component.any(_isRawRingFragment)) {
        blocked.addAll(component);
        continue;
      }
      if (component.any(_isLegacyRingArchive)) {
        // Old manifests can contain cumulative overlapping archives. Select
        // one exact, nonduplicating path for upload, but never treat that
        // legacy range as durable ADVANCE coverage.
        final exactTile = _exactRecoveryUploadTile(component);
        if (exactTile == null) {
          blocked.addAll(component);
        } else {
          blocked.addAll(
            component.where((wal) => !exactTile.contains(wal)),
          );
        }
        continue;
      }
      if (!_hasNonOverlappingRecoverySequence(component)) {
        blocked.addAll(component);
      }
    }
  }
  return blocked;
}

Set<Wal> _permanentlyBlockedLegacyRecoveryArtifacts(
  List<Wal> pending, {
  required int conversationBoundarySeconds,
}) {
  final blocked = Set<Wal>.identity();
  final recoveryGroups = _continuousRingRecoveryGroups(
    pending.where(
      (wal) => wal.conversationId == null && _isRingRecoveryArtifact(wal),
    ),
    conversationBoundarySeconds: conversationBoundarySeconds,
  );
  for (final group in recoveryGroups) {
    for (final component in _recoverySequenceComponents(group)) {
      if (component.any(_isRawRingFragment) || !component.any(_isLegacyRingArchive)) {
        continue;
      }
      if (_exactRecoveryUploadTile(component) == null) {
        blocked.addAll(component);
      }
    }
  }
  return blocked;
}

Set<Wal> _legacyAliasesCoveredByBatch(
  List<Wal> pending,
  List<Wal> batch, {
  required int conversationBoundarySeconds,
}) {
  final batchSet = Set<Wal>.identity()..addAll(batch);
  final coveredAliases = Set<Wal>.identity();
  final recoveryGroups = _continuousRingRecoveryGroups(
    pending.where(
      (wal) => wal.conversationId == null && _isRingRecoveryArtifact(wal),
    ),
    conversationBoundarySeconds: conversationBoundarySeconds,
  );
  for (final group in recoveryGroups) {
    for (final component in _recoverySequenceComponents(group)) {
      if (!component.any(_isLegacyRingArchive) || component.any(_isRawRingFragment)) {
        continue;
      }
      final exactTile = _exactRecoveryUploadTile(component);
      if (exactTile == null || !exactTile.every(batchSet.contains)) continue;
      coveredAliases.addAll(
        component.where((wal) => !exactTile.contains(wal)),
      );
    }
  }
  return coveredAliases;
}

bool _isAuthorizedHistoricalRecovery(
  Wal wal,
  _AuthorizedRecoveryScope? scope,
) {
  if (scope == null || wal.device != scope.deviceId || wal.conversationId != null || !_isRingRecoveryArtifact(wal)) {
    return false;
  }
  final range = RingProtocol.parseRecoverySourceRange(wal.sourceId)!;
  return range.end <= scope.targetWriteSeq;
}

bool _isEligibleForDrain(
  Wal wal, {
  required int nowSeconds,
  required bool includeBackfill,
  required _AuthorizedRecoveryScope? authorizedRecovery,
}) =>
    includeBackfill ||
    _syncLaneForWal(wal, nowSeconds) == SyncUploadLane.fresh ||
    _isAuthorizedHistoricalRecovery(wal, authorizedRecovery);

@visibleForTesting
Set<String> oversizedFreshConversationIds(List<Wal> pending, int nowSeconds) {
  final counts = <String, int>{};
  for (final wal in pending) {
    if (wal.conversationId != null && _syncLaneForWal(wal, nowSeconds) == SyncUploadLane.fresh) {
      counts.update(
        wal.conversationId!,
        (count) => count + 1,
        ifAbsent: () => 1,
      );
    }
  }
  return counts.entries.where((entry) => entry.value > _captureUploadWalLimit).map((entry) => entry.key).toSet();
}

@visibleForTesting
List<Wal> nextSyncUploadBatch(
  List<Wal> pending,
  int nowSeconds, {
  Set<String> forcedBackfillConversationIds = const {},
  int conversationBoundarySeconds = _defaultConversationBoundarySeconds,
}) {
  SyncUploadLane effectiveLane(Wal wal) =>
      wal.conversationId != null && forcedBackfillConversationIds.contains(wal.conversationId)
          ? SyncUploadLane.backfill
          : _syncLaneForWal(wal, nowSeconds);

  final blockedRecoveryArtifacts = _blockedUnassembledRecoveryArtifacts(
    pending,
    conversationBoundarySeconds: conversationBoundarySeconds,
  );
  final ordered = pending
      .where(
        (wal) =>
            !_isUnboundStorageContinuity(wal) &&
            !_isRawRingFragment(wal) &&
            !_isUnassembledConversationRepair(wal) &&
            !blockedRecoveryArtifacts.contains(wal),
      )
      .toList()
    ..sort((a, b) {
      final laneCompare = effectiveLane(
        a,
      ).index.compareTo(effectiveLane(b).index);
      if (laneCompare != 0) return laneCompare;
      return b.timerStart.compareTo(a.timerStart);
    });
  if (ordered.isEmpty) return const [];
  final lane = effectiveLane(ordered.first);
  final conversationId = ordered.first.conversationId;
  final canonicalReplacement = ordered.first.canonicalReplacement;
  final matching = ordered
      .where(
        (wal) =>
            effectiveLane(wal) == lane &&
            wal.conversationId == conversationId &&
            wal.canonicalReplacement == canonicalReplacement,
      )
      .toList();
  if (conversationId == null && _isRingRecoveryArtifact(ordered.first)) {
    final recoveryRun = _continuousRingRecoveryGroups(
      matching.where(_isRingRecoveryArtifact),
      conversationBoundarySeconds: conversationBoundarySeconds,
    ).firstWhere(
      (run) => run.any((wal) => identical(wal, ordered.first)),
    );
    // Physical archives remain bounded, but every configured-timeout logical
    // conversation is one ordered multipart job. The backend therefore sees
    // one capture instead of one conversation per arbitrary archive boundary.
    return recoveryRun;
  }
  return matching.take(conversationId == null ? _syncUploadBatchLimit : _captureUploadWalLimit).toList();
}

({int start, int end})? _ringSourceRange(Wal wal) {
  final match = RegExp(r'^ring_(\d+)_(\d+)$').firstMatch(wal.sourceId ?? '');
  if (match == null) return null;
  final start = int.tryParse(match.group(1)!);
  final end = int.tryParse(match.group(2)!);
  if (start == null || end == null || end <= start) return null;
  return (start: start, end: end);
}

bool _sameUploadEncoding(Wal left, Wal right) =>
    left.device == right.device &&
    left.codec == right.codec &&
    left.sampleRate == right.sampleRate &&
    left.channel == right.channel &&
    left.frameSize == right.frameSize &&
    left.conversationId == right.conversationId &&
    left.uploadIntent == right.uploadIntent;

/// Immutable source WALs stay as the acknowledgement/retry records. This
/// grouping only determines the larger derived artifacts exposed to STT.
@visibleForTesting
List<List<Wal>> contiguousWalUploadRuns(
  List<Wal> wals, {
  int maxArtifactSeconds = 300,
}) {
  final ordered = List<Wal>.from(wals)
    ..sort((a, b) {
      final left = _ringSourceRange(a);
      final right = _ringSourceRange(b);
      if (left != null && right != null && a.device == b.device) {
        final sourceCompare = left.start.compareTo(right.start);
        if (sourceCompare != 0) return sourceCompare;
      }
      final timeCompare = a.timerStart.compareTo(b.timerStart);
      if (timeCompare != 0) return timeCompare;
      return a.id.compareTo(b.id);
    });

  final runs = <List<Wal>>[];
  for (final wal in ordered) {
    final source = _ringSourceRange(wal);
    if (runs.isEmpty || source == null) {
      runs.add([wal]);
      continue;
    }

    final run = runs.last;
    final previous = run.last;
    final previousSource = _ringSourceRange(previous);
    final fps = wal.codec.getFramesPerSecond();
    final runFrames = run.fold<int>(0, (sum, member) => sum + member.totalFrames);
    final nextDuration = fps > 0 ? (runFrames + wal.totalFrames) / fps : double.infinity;
    final wallGap = wal.timerStart - _walEndSeconds(previous);
    final joins = previousSource != null &&
        previousSource.end == source.start &&
        _sameUploadEncoding(previous, wal) &&
        wallGap >= -2 &&
        wallGap <= 2 &&
        nextDuration <= maxArtifactSeconds;
    if (joins) {
      run.add(wal);
    } else {
      runs.add([wal]);
    }
  }
  return runs;
}

class _PreparedUploadFiles {
  const _PreparedUploadFiles(this.files, this.temporaryFiles);

  final List<File> files;
  final List<File> temporaryFiles;
}

class _HistoricalRingArchive {
  const _HistoricalRingArchive({
    required this.sources,
    required this.wal,
    this.createdFile,
  });

  final List<Wal> sources;
  final Wal wal;
  final File? createdFile;
}

class _CanonicalSourceSnapshotChanged implements Exception {
  const _CanonicalSourceSnapshotChanged();
}

class LocalWalSyncImpl implements LocalWalSync {
  List<Wal> _wals = [];

  List<WalFrame> _frames = [];
  List<bool> _frameSynced = [];

  Timer? _chunkingTimer;
  Timer? _flushingTimer;

  IWalSyncListener listener;

  int _framesPerSecond = 100;
  BleAudioCodec _codec = BleAudioCodec.opus;
  String? _deviceId;
  String? _deviceModel;

  bool _isCancelled = false;

  /// Completes when _initializeWals() finishes loading WALs from disk.
  final Completer<void> _walReady = Completer<void>();

  /// Future that resolves when WALs are loaded and ready to query.
  Future<void> get walReady => _walReady.future;

  /// Accumulated conversation IDs from completed batches during an ongoing sync.
  /// Accessible so that cancel can retrieve partial results.
  SyncLocalFilesResponse? _accumulatedResponse;
  SyncLocalFilesResponse? get accumulatedResponse => _accumulatedResponse;

  final SyncUploadGate? _uploadGateOverride;
  SyncUploadGate get _uploadGate => _uploadGateOverride ?? SyncUploadGate.instance;
  final WalPersister? _walPersisterOverride;
  final WalPathResolver _walPathResolver;
  final OpusSilenceFrameFactory _silenceFrameFactory;
  final SyncJobStatusFetcher _syncJobStatusFetcher;
  final ConversationBoundarySecondsProvider _conversationBoundarySecondsProvider;
  final Mutex _syncMutex = Mutex();
  final Mutex _walAssemblyMutex = Mutex();
  int _externalWalRegistrationsInFlight = 0;
  int _externalWalRegistrationEpoch = 0;
  Completer<void>? _externalWalRegistrationsIdle;
  Future<void>? _freshUploadWake;
  bool _freshUploadWakePending = false;
  String? _freshUploadWakeWalId;
  Timer? _historicalCompactionTimer;
  Future<void>? _historicalCompaction;

  LocalWalSyncImpl(
    this.listener, {
    SyncUploadGate? uploadGate,
    WalPersister? walPersister,
    WalPathResolver? walPathResolver,
    OpusSilenceFrameFactory? silenceFrameFactory,
    SyncJobStatusFetcher? syncJobStatusFetcher,
    ConversationBoundarySecondsProvider? conversationBoundarySecondsProvider,
  })  : _uploadGateOverride = uploadGate,
        _walPersisterOverride = walPersister,
        _walPathResolver = walPathResolver ?? Wal.getFilePath,
        _silenceFrameFactory = silenceFrameFactory ?? encodeOpusSilenceFrame,
        _syncJobStatusFetcher = syncJobStatusFetcher ?? fetchSyncJobStatus,
        _conversationBoundarySecondsProvider =
            conversationBoundarySecondsProvider ?? (() => SharedPreferencesUtil().conversationSilenceDuration);

  int _conversationBoundarySeconds() {
    return effectiveConversationBoundarySeconds(
      _conversationBoundarySecondsProvider(),
    );
  }

  Future<T> _serializeWalAssembly<T>(
    Future<T> Function() operation,
  ) async {
    await _walAssemblyMutex.acquire();
    try {
      return await operation();
    } finally {
      _walAssemblyMutex.release();
    }
  }

  Future<void> _waitForExternalWalRegistrations() async {
    while (_externalWalRegistrationsInFlight > 0) {
      final idle = _externalWalRegistrationsIdle;
      if (idle == null) continue;
      await idle.future;
    }
  }

  @visibleForTesting
  List<WalFrame> get testFrames => _frames;

  @visibleForTesting
  List<bool> get testFrameSynced => _frameSynced;

  @visibleForTesting
  List<Wal> get testWals => _wals;

  @visibleForTesting
  set testWals(List<Wal> wals) => _wals = wals;

  @override
  void cancelSync() {
    _isCancelled = true;
  }

  @override
  Future<ExternalWalRegistration> addExternalWal(
    Wal wal, {
    bool scheduleUpload = true,
  }) async {
    if (_externalWalRegistrationsInFlight++ == 0) {
      _externalWalRegistrationsIdle = Completer<void>();
    }
    try {
      return await _addExternalWal(
        wal,
        scheduleUpload: scheduleUpload,
      );
    } finally {
      _externalWalRegistrationsInFlight--;
      _externalWalRegistrationEpoch++;
      if (_externalWalRegistrationsInFlight == 0) {
        final idle = _externalWalRegistrationsIdle;
        _externalWalRegistrationsIdle = null;
        if (idle != null && !idle.isCompleted) idle.complete();
      }
    }
  }

  Future<ExternalWalRegistration> _addExternalWal(
    Wal wal, {
    required bool scheduleUpload,
  }) async {
    _inheritCanonicalConversationOwner(wal);
    final existingIndex = _wals.indexWhere((w) => w.id == wal.id);
    if (existingIndex >= 0) {
      final existing = _wals[existingIndex];
      if (existing.status == WalStatus.corrupted &&
          _isDurableRingCoverageArtifact(existing) &&
          _isDurableRingCoverageArtifact(wal) &&
          _sameRingEncoding(existing, wal)) {
        _wals[existingIndex] = wal;
        try {
          await _saveWalsToFile();
        } catch (_) {
          _wals[existingIndex] = existing;
          rethrow;
        }
        listener.onWalUpdated();
        Logger.debug(
          "LocalWalSync: Replaced unavailable ring WAL ${wal.id} from device storage",
        );
        if (scheduleUpload && wal.status == WalStatus.miss && _mayAutoUploadExternalWal(wal)) {
          _scheduleFreshUpload(wal);
        }
        return ExternalWalRegistration.added;
      }
      if (!await _hasIdenticalFile(existing, wal)) {
        throw StateError('External WAL identity collision for ${wal.id}');
      }
      await _upgradeConversationOwnerMetadata(existing, wal);
      await _upgradeCaptureEndMetadata(existing, wal);
      Logger.debug("LocalWalSync: WAL ${wal.id} already durably registered");
      await _deleteDuplicateExternalFile(existing, wal);
      if (scheduleUpload && existing.status == WalStatus.miss && _mayAutoUploadExternalWal(existing)) {
        _scheduleFreshUpload(existing);
      }
      return ExternalWalRegistration.alreadyRegistered;
    }

    // Older ring-sync builds keyed recovered WALs only by timestamp. If one of
    // those files is byte-identical, it is already durable (and may already
    // be uploaded); do not manufacture a second conversation from the retry.
    for (final existing in _wals) {
      if (existing.device == wal.device &&
          existing.timerStart == wal.timerStart &&
          existing.codec == wal.codec &&
          existing.originalStorage == wal.originalStorage &&
          await _hasIdenticalFile(existing, wal)) {
        // Legacy archives are valid audio/upload inputs, but their source
        // range may span a sequence hole. They cannot suppress a truthful raw
        // reread after upgrade even when their bytes happen to match.
        if (_isLegacyRingArchive(existing) && _isDurableRingCoverageArtifact(wal)) {
          continue;
        }
        // Old builds could overwrite a timestamp-named file after it had been
        // marked synced. Without the upload-time hash, its current bytes are
        // not proof of what reached the server. Re-register that legacy data
        // conservatively; source-aware WALs below are immutable and idempotent.
        if (existing.sourceId == null && existing.status == WalStatus.synced) {
          Logger.debug(
            "LocalWalSync: synced legacy WAL ${existing.id} has no immutable upload proof; retaining retry",
          );
          continue;
        }
        Logger.debug(
          "LocalWalSync: external WAL ${wal.id} matches legacy durable WAL ${existing.id}",
        );
        await _upgradeConversationOwnerMetadata(existing, wal);
        await _upgradeCaptureEndMetadata(existing, wal);
        await _deleteDuplicateExternalFile(existing, wal);
        return ExternalWalRegistration.alreadyRegistered;
      }
    }

    _wals.add(wal);
    try {
      await _saveWalsToFile();
    } catch (_) {
      _wals.removeWhere((candidate) => identical(candidate, wal));
      rethrow;
    }
    listener.onWalUpdated();
    Logger.debug(
      "LocalWalSync: Added external WAL ${wal.id} (${wal.seconds}s)",
    );
    if (scheduleUpload &&
        _mayAutoUploadExternalWal(wal) &&
        _syncLaneForWal(wal, DateTime.now().millisecondsSinceEpoch ~/ 1000) == SyncUploadLane.fresh) {
      // Registration is the durability boundary used by device-storage sync:
      // once the manifest is committed, the device may advance its read
      // pointer. Cloud latency must not hold that acknowledgement hostage.
      _scheduleFreshUpload(wal);
    }
    return ExternalWalRegistration.added;
  }

  void _inheritCanonicalConversationOwner(Wal recovered) {
    if (recovered.conversationId != null || !_isRingRecoveryArtifact(recovered)) {
      return;
    }
    final boundarySeconds = _conversationBoundarySeconds();
    final candidates = <({Wal wal, double gap})>[];
    for (final canonical in _wals) {
      if (canonical.device != recovered.device ||
          canonical.conversationId == null ||
          canonical.sourceId?.startsWith('canonical_') != true) {
        continue;
      }
      final gap = _wallIntervalGapSeconds(canonical, recovered);
      if (gap < boundarySeconds) {
        candidates.add((wal: canonical, gap: gap));
      }
    }
    if (candidates.isEmpty) return;
    candidates.sort((left, right) => left.gap.compareTo(right.gap));
    final nearestGap = candidates.first.gap;
    final nearestOwners = candidates
        .where((candidate) => candidate.gap == nearestGap)
        .map((candidate) => candidate.wal.conversationId!)
        .toSet();
    if (nearestOwners.length != 1) {
      DebugLogManager.logWarning(
        'LocalWalSync: recovered ring range has ambiguous canonical ownership; preserving it unowned',
        {
          'walId': recovered.id,
          'sourceId': recovered.sourceId,
          'candidateOwnerCount': nearestOwners.length,
          'nearestGapSeconds': nearestGap,
        },
      );
      return;
    }
    recovered.conversationId = nearestOwners.single;
  }

  double _wallIntervalGapSeconds(Wal left, Wal right) {
    if (right.timerStart > left.wallClockEndSeconds) {
      return right.timerStart - left.wallClockEndSeconds;
    }
    if (left.timerStart > right.wallClockEndSeconds) {
      return left.timerStart - right.wallClockEndSeconds;
    }
    return 0;
  }

  Future<void> _upgradeConversationOwnerMetadata(
    Wal existing,
    Wal recovered,
  ) async {
    final recoveredOwner = recovered.conversationId;
    if (recoveredOwner == null || existing.conversationId == recoveredOwner) {
      return;
    }
    if (existing.conversationId != null) {
      throw StateError(
        'External WAL ${existing.id} conflicts with canonical conversation ownership',
      );
    }
    existing.conversationId = recoveredOwner;
    try {
      await _saveWalsToFile();
    } catch (_) {
      existing.conversationId = null;
      rethrow;
    }
    listener.onWalUpdated();
  }

  Future<void> _upgradeCaptureEndMetadata(Wal existing, Wal recovered) async {
    if (existing.validatedCaptureEndSeconds != null) return;
    final recoveredEnd = recovered.validatedCaptureEndSeconds;
    if (recoveredEnd == null) return;
    final previous = existing.captureEndSeconds;
    existing.captureEndSeconds = recoveredEnd;
    try {
      await _saveWalsToFile();
    } catch (_) {
      existing.captureEndSeconds = previous;
      rethrow;
    }
    listener.onWalUpdated();
  }

  bool _mayAutoUploadExternalWal(Wal wal) {
    // Ring-tail fallback ranges are transport recovery units, not independent
    // conversations. Uploading them before the live session receives its
    // server conversation id creates parallel jobs of 1–3 second utterances;
    // those jobs race conversation assignment and repeatedly reprocess
    // summaries. Keep the bytes durable on the phone until
    // stampConversationId() binds the complete session to its authoritative
    // backend conversation.
    return !_isRawRingFragment(wal);
  }

  void _scheduleFreshUpload(Wal wal) {
    _freshUploadWakePending = true;
    _freshUploadWakeWalId = wal.id;
    if (_freshUploadWake != null) return;
    _startFreshUploadWake();
  }

  void _startFreshUploadWake() {
    final wake = _drainFreshUploadWakes();
    _freshUploadWake = wake;
    unawaited(
      wake.whenComplete(() {
        if (!identical(_freshUploadWake, wake)) return;
        _freshUploadWake = null;
        // A registration can land after the drain's final pending check but
        // before this completion callback. Preserve that wake as a new drain.
        if (_freshUploadWakePending) _startFreshUploadWake();
      }),
    );
  }

  Future<void> _drainFreshUploadWakes() async {
    do {
      _freshUploadWakePending = false;
      final walId = _freshUploadWakeWalId;
      try {
        // Device-storage recovery persists one WAL at a time. Coalesce wakes
        // so a fast BLE drain cannot start duplicate upload loops.
        await syncFreshOnly();
      } catch (error) {
        Logger.debug(
          'LocalWalSync: fresh upload wake failed for $walId: $error',
        );
      }
    } while (_freshUploadWakePending);
  }

  Future<bool> _hasIdenticalFile(Wal existing, Wal candidate) async {
    if (existing.filePath == null || candidate.filePath == null) return false;
    final existingPath = await _walPathResolver(existing.filePath);
    final candidatePath = await _walPathResolver(candidate.filePath);
    if (existingPath == null || candidatePath == null) return false;
    final existingFile = File(existingPath);
    final candidateFile = File(candidatePath);
    if (!await existingFile.exists() || !await candidateFile.exists()) return false;
    if (await existingFile.length() != await candidateFile.length()) return false;
    if (existingPath == candidatePath) return true;

    final existingBytes = await existingFile.readAsBytes();
    final candidateBytes = await candidateFile.readAsBytes();
    return listEquals(existingBytes, candidateBytes);
  }

  Future<void> _deleteDuplicateExternalFile(Wal existing, Wal candidate) async {
    if (existing.filePath == null || candidate.filePath == null || existing.filePath == candidate.filePath) return;
    final candidatePath = await _walPathResolver(candidate.filePath);
    if (candidatePath == null) return;
    final candidateFile = File(candidatePath);
    if (await candidateFile.exists()) await candidateFile.delete();
  }

  Future<_PreparedUploadFiles> _prepareUploadFiles(
    List<Wal> wals,
    List<File> sourceFiles,
  ) async {
    final filesByWal = Map<Wal, File>.identity();
    for (var index = 0; index < wals.length; index++) {
      filesByWal[wals[index]] = sourceFiles[index];
    }

    final uploadFiles = <File>[];
    final temporaryFiles = <File>[];
    for (final run in contiguousWalUploadRuns(wals)) {
      if (run.length == 1) {
        uploadFiles.add(filesByWal[run.single]!);
        continue;
      }

      final first = run.first;
      final firstRange = _ringSourceRange(first)!;
      final lastRange = _ringSourceRange(run.last)!;
      final filename = first.getFileNameByTimeStarts(
        first.timerStart,
        sourceId: 'assembled_${firstRange.start}_${lastRange.end}_$pid',
      );
      final artifact = File('${Directory.systemTemp.path}/$filename');
      final partial = File('${artifact.path}.partial');
      if (await artifact.exists()) await artifact.delete();
      if (await partial.exists()) await partial.delete();
      final sink = partial.openWrite();
      var sinkClosed = false;
      try {
        for (final wal in run) {
          await sink.addStream(filesByWal[wal]!.openRead());
        }
        await sink.flush();
        await sink.close();
        sinkClosed = true;
        await partial.rename(artifact.path);
      } catch (_) {
        if (!sinkClosed) {
          try {
            await sink.close();
          } catch (_) {
            // Preserve the assembly failure; cleanup is best-effort.
          }
        }
        if (await partial.exists()) await partial.delete();
        if (await artifact.exists()) await artifact.delete();
        rethrow;
      }
      uploadFiles.add(artifact);
      temporaryFiles.add(artifact);
    }
    return _PreparedUploadFiles(uploadFiles, temporaryFiles);
  }

  Future<void> _deleteTemporaryUploadFiles(List<File> files) async {
    for (final file in files) {
      try {
        if (await file.exists()) await file.delete();
      } catch (error) {
        Logger.debug('LocalWalSync: failed to delete derived upload artifact: $error');
      }
    }
  }

  @override
  void start() {
    _initializeWals();
    _chunkingTimer = Timer.periodic(
      const Duration(seconds: chunkSizeInSeconds + newFrameSyncDelaySeconds),
      (t) async {
        await _chunk();
      },
    );
    _flushingTimer = Timer.periodic(
      const Duration(
        seconds: flushIntervalInSeconds + newFrameSyncDelaySeconds,
      ),
      (t) async {
        await _flush();
      },
    );
    _historicalCompactionTimer = Timer.periodic(
      const Duration(seconds: 30),
      (_) => _scheduleHistoricalCompaction(),
    );
  }

  Future<void> _initializeWals() async {
    await WalFileManager.init();
    _wals = await WalFileManager.loadWals();
    Logger.debug("wal service start: ${_wals.length}");

    final missingCount = _wals.where((w) => w.status == WalStatus.miss).length;
    final syncedCount = _wals.where((w) => w.status == WalStatus.synced).length;
    DebugLogManager.logEvent('wal_initialized', {
      'totalWals': _wals.length,
      'missing': missingCount,
      'synced': syncedCount,
    });

    // Run migrations for legacy Limitless files
    final migratedCount = await WalFileManager.migrateLegacyLimitlessFiles(
      _wals,
    );
    if (migratedCount > 0) {
      // Reload WALs after migration
      _wals = await WalFileManager.loadWals();
      Logger.debug("wal service after migration: ${_wals.length}");
      DebugLogManager.logInfo('WAL migration completed', {
        'migratedCount': migratedCount,
        'totalAfter': _wals.length,
      });
    }

    // Fix any inconsistent WAL states from old implementations
    await WalFileManager.migrateInconsistentWals(_wals);
    if (!_walReady.isCompleted) _walReady.complete();
    listener.onWalUpdated();
    _scheduleHistoricalCompaction();
  }

  @visibleForTesting
  Future<void> prepareHistoricalRingFragments({
    required int nowSeconds,
    String? recoveryDeviceId,
    int? recoverySequenceBoundary,
    int? conversationBoundarySeconds,
  }) {
    if ((recoveryDeviceId == null) != (recoverySequenceBoundary == null)) {
      throw ArgumentError('Recovery compaction boundary requires both device and sequence');
    }
    final boundarySeconds = conversationBoundarySeconds ?? _conversationBoundarySeconds();
    final inFlight = _historicalCompaction;
    if (inFlight != null) {
      if (recoveryDeviceId == null) return inFlight;
      return inFlight.then(
        (_) => prepareHistoricalRingFragments(
          nowSeconds: nowSeconds,
          recoveryDeviceId: recoveryDeviceId,
          recoverySequenceBoundary: recoverySequenceBoundary,
          conversationBoundarySeconds: boundarySeconds,
        ),
      );
    }
    late final Future<void> operation;
    operation = _serializeWalAssembly(
      () => _prepareHistoricalRingFragments(
        nowSeconds: nowSeconds,
        recoveryDeviceId: recoveryDeviceId,
        recoverySequenceBoundary: recoverySequenceBoundary,
        conversationBoundarySeconds: boundarySeconds,
      ),
    ).whenComplete(() {
      if (identical(_historicalCompaction, operation)) {
        _historicalCompaction = null;
      }
    });
    _historicalCompaction = operation;
    return operation;
  }

  Future<void> _prepareHistoricalRingFragments({
    required int nowSeconds,
    required String? recoveryDeviceId,
    required int? recoverySequenceBoundary,
    required int conversationBoundarySeconds,
  }) async {
    final candidateSnapshot = _wals
        .where(
          (wal) =>
              wal.conversationId == null &&
              _isDurableRingCoverageArtifact(wal) &&
              wal.storage == WalStorage.disk &&
              (wal.status == WalStatus.miss || wal.status == WalStatus.synced),
        )
        .toList();
    final candidates = <Wal>[];
    final unavailable = <Wal>[];
    final unavailableStatuses = <Wal, WalStatus>{};
    for (final wal in candidateSnapshot) {
      try {
        final path = await _walPathResolver(wal.filePath);
        if (path != null) {
          final file = File(path);
          if (await file.exists() && await file.length() > 0) {
            candidates.add(wal);
            continue;
          }
        }
      } catch (_) {
        // A local source that cannot be opened is not retryable compaction
        // work. The pendant's immutable sequence remains the recovery owner.
      }
      unavailableStatuses[wal] = wal.status;
      unavailable.add(wal);
    }
    if (unavailable.isNotEmpty) {
      for (final wal in unavailable) {
        wal.markCorrupted();
      }
      try {
        await _saveWalsToFile();
      } catch (_) {
        for (final wal in unavailable) {
          wal.status = unavailableStatuses[wal]!;
        }
        rethrow;
      }
      DebugLogManager.logWarning(
        'Historical ring sources unavailable; waiting for pendant recovery',
        {'count': unavailable.length},
      );
      listener.onWalUpdated();
    }
    final buckets = <String, List<Wal>>{};
    for (final wal in candidates) {
      final key = [
        wal.device,
        wal.codec.name,
        wal.sampleRate,
        wal.channel,
        wal.frameSize,
      ].join('|');
      buckets.putIfAbsent(key, () => []).add(wal);
    }

    final archives = <_HistoricalRingArchive>[];
    for (final bucket in buckets.values) {
      bucket.sort((left, right) {
        final timeCompare = left.timerStart.compareTo(right.timerStart);
        if (timeCompare != 0) return timeCompare;
        return left.id.compareTo(right.id);
      });
      for (final capture in _continuousRingRecoveryGroups(
        bucket,
        conversationBoundarySeconds: conversationBoundarySeconds,
      )) {
        final captureEnd = capture.map(_walEndSeconds).reduce(max);
        if (nowSeconds - captureEnd < conversationBoundarySeconds) {
          continue;
        }
        final sequenceBoundary = capture.first.device == recoveryDeviceId ? recoverySequenceBoundary : null;
        for (final group in _continuousRingRecoveryGroups(
          capture,
          conversationBoundarySeconds: conversationBoundarySeconds,
          maxWallSeconds: 30 * 60,
          requireContiguousSequence: true,
          sequenceBoundary: sequenceBoundary,
        )) {
          if (sequenceBoundary != null &&
              group.any(
                (wal) => _sequenceBoundarySide(wal, sequenceBoundary) == 0,
              )) {
            // A source file itself straddles the receipt. Without per-record
            // byte offsets it cannot be sliced safely, so retain it verbatim
            // for a later receipt rather than manufacturing false coverage.
            continue;
          }
          // A bounded archive is already the desired physical representation.
          // It remains part of the logical capture above so a later adjacent
          // archive/raw range can roll it forward, but it need not be rewritten
          // on every compaction pass.
          if (group.length == 1 && !_isRawRingFragment(group.single)) {
            continue;
          }
          try {
            archives.add(
              await _prepareHistoricalRingArchive(
                group,
                sequenceBoundary: sequenceBoundary,
                conversationBoundarySeconds: conversationBoundarySeconds,
              ),
            );
          } catch (error) {
            Logger.debug(
              'LocalWalSync: historical archive group remains retryable: $error',
            );
          }
        }
      }
    }
    if (archives.isEmpty) return;

    final producedCoverage = <String, RingSequenceCoverage>{};
    for (final archive in archives) {
      final range = RingProtocol.parseDurableCoverageSourceRange(archive.wal.sourceId)!;
      producedCoverage.putIfAbsent(_ringEncodingBucket(archive.wal), RingSequenceCoverage.new).add(
            range.start,
            range.end,
          );
    }
    final supersededLegacyArchives = _wals.where((wal) {
      if (wal.conversationId != null ||
          wal.storage != WalStorage.disk ||
          (wal.status != WalStatus.miss && wal.status != WalStatus.synced) ||
          !_isLegacyRingArchive(wal)) {
        return false;
      }
      final range = RingProtocol.parseRecoverySourceRange(wal.sourceId)!;
      return producedCoverage[_ringEncodingBucket(wal)]?.covers(range.start, range.end) == true;
    }).toSet();
    final supersededCorruptedArtifacts = _wals.where((wal) {
      if (wal.conversationId != null ||
          wal.storage != WalStorage.disk ||
          wal.status != WalStatus.corrupted ||
          !_isDurableRingCoverageArtifact(wal)) {
        return false;
      }
      final range = RingProtocol.parseDurableCoverageSourceRange(wal.sourceId)!;
      return producedCoverage[_ringEncodingBucket(wal)]?.covers(range.start, range.end) == true;
    }).toSet();
    final compactedSources = {
      ...archives.expand((archive) => archive.sources),
      ...supersededLegacyArchives,
      ...supersededCorruptedArtifacts,
    };
    _wals = [
      ..._wals.where((wal) => !compactedSources.contains(wal)),
      ...archives.map((archive) => archive.wal),
    ];
    try {
      await _saveWalsToFile();
    } catch (_) {
      // Publishing the manifest is the archive ownership commit. Restore the
      // immutable sources without replacing the whole list: an external WAL
      // may have registered while the failed archive write awaited disk.
      final archiveWals = archives.map((archive) => archive.wal).toSet();
      final restored = _wals.where((wal) => !archiveWals.contains(wal)).toList();
      final tracked = Set<Wal>.identity()..addAll(restored);
      for (final source in compactedSources) {
        if (tracked.add(source)) restored.add(source);
      }
      _wals = restored;
      try {
        // WalFileManager serializes snapshots in invocation order. A
        // registration that started while the failed archive write awaited
        // may already have queued a newer snapshot containing that
        // uncommitted archive. Queue restored ownership after it as the final
        // durable barrier before removing the archive artifact.
        await _saveWalsToFile();
      } finally {
        await _deleteHistoricalArchiveFiles(archives);
      }
      rethrow;
    }

    final retainedPaths = archives.map((archive) => archive.wal.filePath).whereType<String>().toSet();
    for (final source in compactedSources) {
      if (retainedPaths.contains(source.filePath)) continue;
      final path = await _walPathResolver(source.filePath);
      if (path == null) continue;
      try {
        final file = File(path);
        if (await file.exists()) await file.delete();
      } catch (error) {
        Logger.debug(
          'LocalWalSync: historical source cleanup failed: $error',
        );
      }
    }
    DebugLogManager.logEvent('historical_ring_archive_compacted', {
      'source_fragment_count': compactedSources.length,
      'archive_artifact_count': archives.length,
      'legacy_archive_retired_count': supersededLegacyArchives.length,
      'corrupted_artifact_recovered_count': supersededCorruptedArtifacts.length,
    });
    listener.onWalUpdated();
  }

  Future<_HistoricalRingArchive> _prepareHistoricalRingArchive(
    List<Wal> sources, {
    int? sequenceBoundary,
    required int conversationBoundarySeconds,
  }) async {
    if (sources.isEmpty) {
      throw ArgumentError.value(sources, 'sources', 'must not be empty');
    }
    final contiguousRanges = _orderedRecoveryRanges(sources);
    if (contiguousRanges.length != sources.length) {
      throw StateError('Historical archive requires pendant sequence identity');
    }
    var coveredEnd = contiguousRanges.first.end;
    for (final range in contiguousRanges.skip(1)) {
      if (range.start > coveredEnd) {
        throw StateError('Historical archive cannot claim an uncovered pendant sequence');
      }
      if (range.end > coveredEnd) coveredEnd = range.end;
    }
    if (sequenceBoundary != null && contiguousRanges.first.start < sequenceBoundary && coveredEnd > sequenceBoundary) {
      throw StateError('Historical archive cannot cross an authorized receipt boundary');
    }
    final orderedBySequence = List<Wal>.from(sources)
      ..sort(
        (left, right) => RingProtocol.parseRecoverySourceRange(left.sourceId)!.start.compareTo(
              RingProtocol.parseRecoverySourceRange(right.sourceId)!.start,
            ),
      );
    final first = orderedBySequence.first;
    final sourceRanges = orderedBySequence.map((wal) => RingProtocol.parseRecoverySourceRange(wal.sourceId)!).toList();
    final archiveStart = sourceRanges.map((range) => range.start).reduce(min);
    final archiveEnd = sourceRanges.map((range) => range.end).reduce(max);
    final archiveSourceId = 'archive2_ring_${archiveStart}_${archiveEnd}_${first.timerStart}';
    final archiveStatus = sources.any((wal) => wal.status == WalStatus.miss) ? WalStatus.miss : WalStatus.synced;

    if (sources.length == 1) {
      return _HistoricalRingArchive(
        sources: sources,
        wal: _historicalArchiveWal(
          first: first,
          sourceId: archiveSourceId,
          filePath: first.filePath,
          timerStart: first.timerStart,
          totalFrames: first.totalFrames,
          captureEndSeconds: first.wallClockEndSeconds,
          status: archiveStatus,
        ),
      );
    }

    final firstPath = await _walPathResolver(first.filePath);
    if (firstPath == null) {
      throw StateError('Historical archive destination is unavailable');
    }
    final destination = File(
      '${File(firstPath).parent.path}/${first.getFileNameByTimeStarts(first.timerStart, sourceId: archiveSourceId)}',
    );
    final parts = <ConversationAudioPart>[];
    for (final wal in sources) {
      final path = await _walPathResolver(wal.filePath);
      if (path == null || !await File(path).exists()) {
        throw StateError('Historical archive source is unavailable');
      }
      parts.add(ConversationAudioPart(wal: wal, file: File(path)));
    }
    final assembly = await assembleConversationAudio(
      parts: parts,
      destination: destination,
      silenceFrameFactory: _silenceFrameFactory,
      conversationBoundarySeconds: conversationBoundarySeconds,
    );
    final fps = first.codec.getFramesPerSecond();
    return _HistoricalRingArchive(
      sources: sources,
      createdFile: assembly.file,
      wal: _historicalArchiveWal(
        first: first,
        sourceId: archiveSourceId,
        filePath: assembly.file.path.split('/').last,
        timerStart: assembly.timerStart,
        totalFrames: assembly.totalFrames,
        captureEndSeconds: assembly.captureEndSeconds,
        seconds: fps > 0 ? (assembly.totalFrames + fps - 1) ~/ fps : 0,
        status: archiveStatus,
      ),
    );
  }

  Wal _historicalArchiveWal({
    required Wal first,
    required String sourceId,
    required String? filePath,
    required int timerStart,
    required int totalFrames,
    required double captureEndSeconds,
    required WalStatus status,
    int? seconds,
  }) {
    final fps = first.codec.getFramesPerSecond();
    return Wal(
      timerStart: timerStart,
      codec: first.codec,
      channel: first.channel,
      sampleRate: first.sampleRate,
      seconds: seconds ?? (fps > 0 ? (totalFrames + fps - 1) ~/ fps : first.seconds),
      captureEndSeconds: captureEndSeconds,
      totalFrames: totalFrames,
      status: status,
      storage: WalStorage.disk,
      originalStorage: WalStorage.sdcard,
      filePath: filePath,
      device: first.device,
      deviceModel: first.deviceModel,
      sourceId: sourceId,
      uploadIntent: WalUploadIntent.historicalBackfill,
      retryCount: first.retryCount,
      lastRetryAt: first.lastRetryAt,
    );
  }

  Future<void> _deleteHistoricalArchiveFiles(
    List<_HistoricalRingArchive> archives,
  ) async {
    for (final archive in archives) {
      final file = archive.createdFile;
      if (file == null) continue;
      try {
        if (await file.exists()) await file.delete();
      } catch (_) {}
    }
  }

  void _scheduleHistoricalCompaction() {
    unawaited(
      prepareHistoricalRingFragments(
        nowSeconds: DateTime.now().millisecondsSinceEpoch ~/ 1000,
      ).catchError((Object error) {
        Logger.debug(
          'LocalWalSync: historical compaction remains retryable: $error',
        );
      }),
    );
  }

  @override
  Future stop() async {
    _chunkingTimer?.cancel();
    _flushingTimer?.cancel();
    _historicalCompactionTimer?.cancel();

    await _chunk();
    await _flush();
    await _historicalCompaction;

    _frames = [];
    _frameSynced = [];
  }

  @override
  Future onAudioCodecChanged(BleAudioCodec codec) async {
    // Always chunk+flush+clear to ensure clean session boundaries.
    // This is safe when frames are empty (_chunk returns immediately).
    await _chunk();
    await _flush();
    _frames = [];
    _frameSynced = [];

    _framesPerSecond = codec.getFramesPerSecond();
    _codec = codec;
  }

  @override
  void setDeviceInfo(String? deviceId, String? deviceModel) {
    _deviceId = deviceId;
    _deviceModel = deviceModel;
  }

  Future _chunk() async {
    if (_frames.isEmpty) {
      Logger.debug("Frames are empty");
      return;
    }

    var lossesThreshold = 10 * _framesPerSecond;
    var timerEnd = DateTime.now().millisecondsSinceEpoch ~/ 1000 - newFrameSyncDelaySeconds;
    var pivot = _frames.length - newFrameSyncDelaySeconds * _framesPerSecond;
    if (pivot <= 0) {
      return;
    }

    var high = pivot;
    var low = 0;
    var chunk = _frames.sublist(low, high).map((f) => f.payload).toList();
    var timerStart = timerEnd - (high - low) ~/ _framesPerSecond;
    var chunkFrameCount = high - low;

    bool shouldStored = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
    if (!shouldStored) {
      bool synced = true;
      var losses = 0;
      for (var i = low; i < high; i++) {
        if (!_frameSynced[i]) {
          losses++;
          if (losses >= lossesThreshold) {
            synced = false;
            break;
          }
        }
      }

      shouldStored = (synced == false);
    }

    if (shouldStored) {
      int syncedOffset = 0;
      for (var i = low; i < high; i++) {
        if (_frameSynced[i]) {
          syncedOffset++;
        } else {
          break;
        }
      }
      Logger.debug(
        "$low - $high - $syncedOffset - $chunkFrameCount - $_framesPerSecond",
      );

      Wal wal;
      var walIdx = _wals.indexWhere(
        (w) => w.timerStart == timerStart && w.device == (_deviceId ?? "omi") && w.codec == _codec,
      );
      if (walIdx < 0) {
        wal = Wal(
          codec: _codec,
          timerStart: timerStart,
          data: chunk,
          storage: WalStorage.mem,
          status: syncedOffset == chunkFrameCount ? WalStatus.synced : WalStatus.miss,
          device: _deviceId ?? "omi",
          deviceModel: _deviceModel ?? "Omi",
          seconds: chunkFrameCount ~/ _framesPerSecond,
          totalFrames: chunkFrameCount,
          syncedFrameOffset: syncedOffset,
        );
        _wals.add(wal);
      } else {
        wal = _wals[walIdx];
        wal.data.addAll(chunk);
        wal.storage = WalStorage.mem;
        wal.totalFrames = chunkFrameCount;
        wal.syncedFrameOffset = syncedOffset;
        wal.status = syncedOffset == chunkFrameCount ? WalStatus.synced : WalStatus.miss;
        _wals[walIdx] = wal;
      }

      if (wal.status == WalStatus.synced) {
        listener.onWalSynced(wal);
      }
      listener.onWalUpdated();
    }

    Logger.debug("_chunk wals ${_wals.length}");

    _frames.removeRange(0, pivot);
    _frameSynced.removeRange(0, pivot);
  }

  Future _flush() async {
    Logger.debug("_flushing");
    int flushedCount = 0;
    for (var i = 0; i < _wals.length; i++) {
      final wal = _wals[i];

      if (wal.storage == WalStorage.mem) {
        String? filePath = await Wal.getFilePath(wal.getFileName());
        if (filePath == null) {
          DebugLogManager.logError(
            'LocalWalSync flush error: Flush failed: cannot get file path',
            null,
            null,
            {'walId': wal.id, 'timerStart': wal.timerStart},
          );
          throw Exception('Flushing to storage failed. Cannot get file path.');
        }

        List<int> data = [];
        for (int i = 0; i < wal.data.length; i++) {
          var frame = wal.data[i];

          final byteFrame = ByteData(frame.length);
          for (int j = 0; j < frame.length; j++) {
            byteFrame.setUint8(j, frame[j]);
          }
          data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
          data.addAll(byteFrame.buffer.asUint8List());
        }
        final file = File(filePath);
        await file.writeAsBytes(data);
        wal.filePath = wal.getFileName();
        wal.storage = WalStorage.disk;

        Logger.debug("_flush file ${wal.filePath}");
        flushedCount++;

        _wals[i] = wal;
      }
    }

    if (flushedCount > 0) {
      DebugLogManager.logInfo('Flushed WALs from memory to disk', {
        'count': flushedCount,
      });
    }

    await _saveWalsToFile();
  }

  Future<void> _saveWalsToFile() async {
    Logger.debug('Saving WALs to file');
    final saved = await (_walPersisterOverride?.call(_wals) ?? WalFileManager.saveWals(_wals));
    if (!saved) {
      throw StateError('WAL manifest persistence failed');
    }
  }

  Future<bool> _deleteWal(Wal wal) async {
    if (wal.filePath != null && wal.filePath!.isNotEmpty) {
      try {
        final fullPath = await Wal.getFilePath(wal.filePath);
        if (fullPath != null) {
          final file = File(fullPath);
          if (file.existsSync()) {
            await file.delete();
          }
        }
      } catch (e) {
        Logger.debug(e.toString());
        return false;
      }
    }

    _wals.removeWhere((w) => w.id == wal.id);
    return true;
  }

  @override
  Future deleteWal(Wal wal) async {
    await _deleteWal(wal);
    listener.onWalUpdated();
  }

  @override
  Future<List<Wal>> getMissingWals() async {
    return _wals.where((w) => w.status == WalStatus.miss).toList();
  }

  @override
  Future<Wal?> getWalById(String id) async {
    for (final wal in _wals) {
      if (wal.id == id) return wal;
    }
    return null;
  }

  /// Returns unsynced WALs whose timerStart falls within [sessionStartSeconds, now].
  /// Used by the live capture screen to show inline audio safety indicators.
  List<Wal> getSessionUnsyncedWals(int sessionStartSeconds) {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    return _wals
        .where(
          (w) =>
              w.status == WalStatus.miss &&
              w.storage == WalStorage.disk &&
              w.timerStart >= sessionStartSeconds &&
              w.timerStart <= now,
        )
        .toList();
  }

  /// Mark a WAL as synced and persist the change to disk.
  Future<void> markWalSyncedAndPersist(Wal wal) async {
    wal.status = WalStatus.synced;
    await _saveWalsToFile();
    listener.onWalUpdated();
  }

  @override
  Future<void> markExternalWalSynced(Wal wal) => markWalSyncedAndPersist(wal);

  /// Force-drain all in-flight frames (including the tail buffer that _chunk() normally
  /// keeps in memory) and flush everything to disk. Call this when a capture session ends
  /// to ensure no audio is lost in memory.
  Future<void> finalizeCurrentSession() async {
    if (_frames.isEmpty) return;

    final high = _frames.length;
    if (high <= 0) return;

    var lossesThreshold = 10 * _framesPerSecond;
    var timerEnd = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    var chunk = _frames.sublist(0, high).map((f) => f.payload).toList();
    var timerStart = timerEnd - high ~/ _framesPerSecond;
    var chunkFrameCount = high;

    // Same shouldStored check as _chunk(): only store if unlimited storage enabled
    // or if significant frame loss detected (meaning WebSocket didn't deliver them).
    bool shouldStored = SharedPreferencesUtil().unlimitedLocalStorageEnabled;
    if (!shouldStored) {
      bool synced = true;
      var losses = 0;
      for (var i = 0; i < high; i++) {
        if (!_frameSynced[i]) {
          losses++;
          if (losses >= lossesThreshold) {
            synced = false;
            break;
          }
        }
      }
      shouldStored = !synced;
    }

    if (shouldStored) {
      int syncedOffset = 0;
      for (var i = 0; i < high; i++) {
        if (_frameSynced[i]) {
          syncedOffset++;
        } else {
          break;
        }
      }

      // Use a distinct timerStart so we don't collide with WALs from _chunk().
      // This is the tail buffer that _chunk() left behind.
      _wals = List.from(_wals)
        ..add(
          Wal(
            codec: _codec,
            timerStart: timerStart,
            data: chunk,
            storage: WalStorage.mem,
            status: syncedOffset == chunkFrameCount ? WalStatus.synced : WalStatus.miss,
            device: _deviceId ?? "omi",
            deviceModel: _deviceModel ?? "Omi",
            seconds: chunkFrameCount ~/ _framesPerSecond,
            totalFrames: chunkFrameCount,
            syncedFrameOffset: syncedOffset,
          ),
        );
    }

    _frames = [];
    _frameSynced = [];

    // Flush all in-memory WALs to disk immediately
    await _flush();
    listener.onWalUpdated();
    Logger.debug(
      'finalizeCurrentSession: drained $chunkFrameCount frames (stored=$shouldStored), flushed to disk',
    );
  }

  /// Stamp all session WALs with the given conversationId and persist to disk.
  /// Ring-backed live ranges are compacted into one canonical recording before
  /// upload. This makes WAL→conversation linkage survive app kill without
  /// retaining or submitting thousands of one-second files.
  Future<void> stampConversationId(
    int sessionStartSeconds,
    String conversationId, {
    required bool hasServerSpeechProof,
    int? sessionEndSeconds,
  }) async {
    if (!hasServerSpeechProof) {
      Logger.debug(
        'stampConversationId: retained audio locally because the conversation has no server speech proof',
      );
      return;
    }
    final sessionEnd = sessionEndSeconds ?? DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final conversationBoundarySeconds = _conversationBoundarySeconds();
    var stamped = 0;
    await _serializeWalAssembly(() async {
      await _waitForExternalWalRegistrations();
      final ringDeviceScope = _wals
          .where(
            (wal) =>
                _isRingRecoveryArtifact(wal) &&
                (wal.conversationId == null || wal.conversationId == conversationId) &&
                _isInBoundedSession(
                  wal,
                  sessionStartSeconds: sessionStartSeconds,
                  sessionEndSeconds: sessionEnd,
                ),
          )
          .map((wal) => wal.device)
          .toSet();
      while (true) {
        await _waitForExternalWalRegistrations();
        final registrationEpoch = _externalWalRegistrationEpoch;
        stamped += _stampBoundedSessionWals(
          sessionStartSeconds: sessionStartSeconds,
          sessionEndSeconds: sessionEnd,
          conversationId: conversationId,
          ringDeviceScope: ringDeviceScope,
          conversationBoundarySeconds: conversationBoundarySeconds,
        );
        final ringSources = _boundedRingSourcesForConversation(
          sessionStartSeconds: sessionStartSeconds,
          sessionEndSeconds: sessionEnd,
          conversationId: conversationId,
          ringDeviceScope: ringDeviceScope,
          conversationBoundarySeconds: conversationBoundarySeconds,
        );
        if (ringSources.isEmpty) {
          if (stamped > 0) await _saveWalsToFile();
          break;
        }
        if (_canonicalWalsForConversation(conversationId).isNotEmpty) {
          // A canonical WAL intentionally drops its source sequence ranges.
          // Without that proof, appending a late range can duplicate audio;
          // replacing it can erase the already-complete transcript. Retain the
          // bound range for a future merge contract instead of guessing.
          await _saveWalsToFile();
          Logger.debug(
            'stampConversationId: retained late bound ring audio for $conversationId because its canonical owner cannot be safely extended',
          );
          break;
        }

        final sourceSnapshot = List<Wal>.from(ringSources);
        try {
          await _compactRingConversation(
            conversationId,
            sourceSnapshot,
            sourceSnapshotIsStable: () =>
                _externalWalRegistrationsInFlight == 0 &&
                _externalWalRegistrationEpoch == registrationEpoch &&
                !_hasUnownedWalInBoundedSession(
                  sessionStartSeconds: sessionStartSeconds,
                  sessionEndSeconds: sessionEnd,
                  conversationId: conversationId,
                  ringDeviceScope: ringDeviceScope,
                  conversationBoundarySeconds: conversationBoundarySeconds,
                ) &&
                _sameIdentityWalSet(
                  sourceSnapshot,
                  _boundedRingSourcesForConversation(
                    sessionStartSeconds: sessionStartSeconds,
                    sessionEndSeconds: sessionEnd,
                    conversationId: conversationId,
                    ringDeviceScope: ringDeviceScope,
                    conversationBoundarySeconds: conversationBoundarySeconds,
                  ),
                ),
          );
          break;
        } on _CanonicalSourceSnapshotChanged {
          // A tail registration completed while disk assembly was in flight.
          // Its timestamp belongs to this already-closed server session, so
          // rebuild from the expanded exact source set before publishing.
          continue;
        } catch (error) {
          // Every immutable source remains in place. Persist its conversation
          // owner, but never upload raw fragments.
          await _saveWalsToFile();
          Logger.debug(
            'stampConversationId: canonical assembly failed for $conversationId: $error',
          );
          break;
        }
      }
    });

    Logger.debug(
      'stampConversationId: stamped $stamped WALs with conversation $conversationId',
    );
    Wal? uploadWakeWal;
    for (final wal in _wals) {
      if (wal.status == WalStatus.miss && wal.conversationId == conversationId && !_isRingRecoveryArtifact(wal)) {
        uploadWakeWal = wal;
        break;
      }
    }
    if (uploadWakeWal != null) {
      // Active-conversation repair is independent of opt-in historical sync.
      // The exact server owner is known, so wake one serialized drain.
      _scheduleFreshUpload(uploadWakeWal);
    }
  }

  bool _isInBoundedSession(
    Wal wal, {
    required int sessionStartSeconds,
    required int sessionEndSeconds,
  }) =>
      _walEndSeconds(wal) >= sessionStartSeconds && wal.timerStart <= sessionEndSeconds;

  bool _isStampableSessionWal(Wal wal) {
    final ringContinuity = _isRingRecoveryArtifact(wal);
    return wal.status == WalStatus.miss || (ringContinuity && wal.status == WalStatus.synced);
  }

  Set<Wal> _ringConversationWindowSources({
    required int sessionStartSeconds,
    required int sessionEndSeconds,
    required String conversationId,
    required Set<String> ringDeviceScope,
    required int conversationBoundarySeconds,
  }) {
    final selected = Set<Wal>.identity();
    final eligible = _wals.where(
      (wal) =>
          _isRingRecoveryArtifact(wal) &&
          ringDeviceScope.contains(wal.device) &&
          (wal.conversationId == null || wal.conversationId == conversationId) &&
          _isStampableSessionWal(wal),
    );
    for (final group in _continuousRingRecoveryGroups(
      eligible,
      conversationBoundarySeconds: conversationBoundarySeconds,
    )) {
      final belongsToSession = group.any(
        (wal) =>
            wal.conversationId == conversationId ||
            _isInBoundedSession(
              wal,
              sessionStartSeconds: sessionStartSeconds,
              sessionEndSeconds: sessionEndSeconds,
            ),
      );
      if (belongsToSession) selected.addAll(group);
    }
    return selected;
  }

  int _stampBoundedSessionWals({
    required int sessionStartSeconds,
    required int sessionEndSeconds,
    required String conversationId,
    required Set<String> ringDeviceScope,
    required int conversationBoundarySeconds,
  }) {
    final ringSessionSources = _ringConversationWindowSources(
      sessionStartSeconds: sessionStartSeconds,
      sessionEndSeconds: sessionEndSeconds,
      conversationId: conversationId,
      ringDeviceScope: ringDeviceScope,
      conversationBoundarySeconds: conversationBoundarySeconds,
    );
    var stamped = 0;
    for (final wal in _wals) {
      final belongsToSession = _isRingRecoveryArtifact(wal)
          ? ringSessionSources.contains(wal)
          : _isInBoundedSession(
              wal,
              sessionStartSeconds: sessionStartSeconds,
              sessionEndSeconds: sessionEndSeconds,
            );
      if (wal.conversationId == null && _isStampableSessionWal(wal) && belongsToSession) {
        wal.conversationId = conversationId;
        stamped++;
      }
    }
    return stamped;
  }

  bool _hasUnownedWalInBoundedSession({
    required int sessionStartSeconds,
    required int sessionEndSeconds,
    required String conversationId,
    required Set<String> ringDeviceScope,
    required int conversationBoundarySeconds,
  }) {
    final ringSessionSources = _ringConversationWindowSources(
      sessionStartSeconds: sessionStartSeconds,
      sessionEndSeconds: sessionEndSeconds,
      conversationId: conversationId,
      ringDeviceScope: ringDeviceScope,
      conversationBoundarySeconds: conversationBoundarySeconds,
    );
    return _wals.any((wal) {
      if (wal.conversationId != null || !_isStampableSessionWal(wal)) {
        return false;
      }
      if (_isRingRecoveryArtifact(wal)) {
        return ringSessionSources.contains(wal);
      }
      return _isInBoundedSession(
        wal,
        sessionStartSeconds: sessionStartSeconds,
        sessionEndSeconds: sessionEndSeconds,
      );
    });
  }

  List<Wal> _boundedRingSourcesForConversation({
    required int sessionStartSeconds,
    required int sessionEndSeconds,
    required String conversationId,
    required Set<String> ringDeviceScope,
    required int conversationBoundarySeconds,
  }) {
    final ringSessionSources = _ringConversationWindowSources(
      sessionStartSeconds: sessionStartSeconds,
      sessionEndSeconds: sessionEndSeconds,
      conversationId: conversationId,
      ringDeviceScope: ringDeviceScope,
      conversationBoundarySeconds: conversationBoundarySeconds,
    );
    return ringSessionSources.where((wal) => wal.conversationId == conversationId).toList();
  }

  List<Wal> _canonicalWalsForConversation(String conversationId) => _wals
      .where(
        (wal) => wal.conversationId == conversationId && wal.sourceId?.startsWith('canonical_') == true,
      )
      .toList();

  bool _sameIdentityWalSet(List<Wal> left, List<Wal> right) {
    if (left.length != right.length) return false;
    final identities = Set<Wal>.identity()..addAll(left);
    return right.every(identities.contains);
  }

  Future<void> _compactRingConversation(
    String conversationId,
    List<Wal> sourceWals, {
    int? conversationBoundarySeconds,
    bool Function()? sourceSnapshotIsStable,
  }) async {
    if (sourceWals.isEmpty) {
      await _saveWalsToFile();
      return;
    }
    if (_canonicalWalsForConversation(conversationId).isNotEmpty) {
      throw StateError(
        'Canonical conversation $conversationId already exists; refusing an unprovable partial replacement',
      );
    }

    final byDevice = <String, List<Wal>>{};
    for (final wal in sourceWals) {
      byDevice.putIfAbsent(wal.device, () => <Wal>[]).add(wal);
    }
    if (byDevice.length != 1) {
      throw StateError('Canonical assembly requires one pendant per conversation');
    }

    final boundarySeconds = conversationBoundarySeconds ?? _conversationBoundarySeconds();
    final canonicalWals = <Wal>[];
    final canonicalFiles = <File>[];
    final compactedSources = <Wal>{};
    try {
      for (final entry in byDevice.entries) {
        final parts = <ConversationAudioPart>[];
        for (final wal in entry.value) {
          final path = await _walPathResolver(wal.filePath);
          if (path == null) {
            throw StateError('Canonical source path is unavailable');
          }
          final file = File(path);
          if (!await file.exists()) {
            throw StateError('Canonical source file is unavailable');
          }
          parts.add(ConversationAudioPart(wal: wal, file: file));
        }

        final first = entry.value.reduce(
          (left, right) {
            final leftRange = RingProtocol.parseRecoverySourceRange(left.sourceId)!;
            final rightRange = RingProtocol.parseRecoverySourceRange(right.sourceId)!;
            return leftRange.start <= rightRange.start ? left : right;
          },
        );
        final filename = first.getFileNameByTimeStarts(
          first.timerStart,
          sourceId: 'canonical_${conversationId}_$pid',
        );
        final firstPath = await _walPathResolver(first.filePath);
        if (firstPath == null) {
          throw StateError('Canonical destination directory is unavailable');
        }
        final destination = File('${File(firstPath).parent.path}/$filename');
        final assembly = await assembleConversationAudio(
          parts: parts,
          destination: destination,
          silenceFrameFactory: _silenceFrameFactory,
          conversationBoundarySeconds: boundarySeconds,
        );
        canonicalFiles.add(assembly.file);
        compactedSources.addAll(assembly.sourceWals);

        final fps = first.codec.getFramesPerSecond();
        canonicalWals.add(
          Wal(
            timerStart: assembly.timerStart,
            codec: first.codec,
            channel: first.channel,
            sampleRate: first.sampleRate,
            seconds: fps > 0 ? (assembly.totalFrames + fps - 1) ~/ fps : 0,
            captureEndSeconds: assembly.captureEndSeconds,
            totalFrames: assembly.totalFrames,
            status: assembly.hadLiveGap ? WalStatus.miss : WalStatus.synced,
            storage: WalStorage.disk,
            originalStorage: WalStorage.sdcard,
            filePath: assembly.file.path.split('/').last,
            device: first.device,
            deviceModel: first.deviceModel,
            sourceId: 'canonical_${conversationId}_$pid',
            conversationId: conversationId,
            uploadIntent: WalUploadIntent.liveContinuity,
            canonicalReplacement: assembly.hadLiveGap,
          ),
        );
      }

      if (sourceWals.any((source) => !_wals.any((wal) => identical(wal, source))) ||
          _canonicalWalsForConversation(conversationId).isNotEmpty ||
          (sourceSnapshotIsStable != null && !sourceSnapshotIsStable())) {
        throw const _CanonicalSourceSnapshotChanged();
      }

      // Assembly performs asynchronous disk reads. Preserve WALs outside the
      // exact, synchronously revalidated source snapshot.
      _wals = [
        ..._wals.where((wal) => !compactedSources.contains(wal)),
        ...canonicalWals,
      ];
      try {
        await _saveWalsToFile();
      } catch (_) {
        // Publishing the manifest is the ownership commit. If it fails, put
        // the immutable sources back without replacing the whole list: an
        // external registration may have completed while persistence awaited.
        final restored = _wals
            .where(
              (wal) => !canonicalWals.any(
                (canonical) => identical(canonical, wal),
              ),
            )
            .toList();
        final tracked = Set<Wal>.identity()..addAll(restored);
        for (final source in compactedSources) {
          if (tracked.add(source)) restored.add(source);
        }
        _wals = restored;
        // WalFileManager serializes snapshots in invocation order. A
        // registration that started while the failed canonical write awaited
        // may already have queued a newer snapshot containing that uncommitted
        // canonical. Queue the restored ownership state after it as the final
        // barrier before the canonical file is removed.
        await _saveWalsToFile();
        rethrow;
      }
    } catch (_) {
      for (final file in canonicalFiles) {
        if (await file.exists()) await file.delete();
      }
      rethrow;
    }

    for (final source in compactedSources) {
      final sourcePath = await _walPathResolver(source.filePath);
      if (sourcePath == null) continue;
      final sourceFile = File(sourcePath);
      if (canonicalFiles.any((file) => file.path == sourceFile.path)) continue;
      try {
        if (await sourceFile.exists()) await sourceFile.delete();
      } catch (error) {
        Logger.debug('Canonical assembly could not delete compacted source: $error');
      }
    }
    listener.onWalUpdated();
  }

  /// Returns WALs that have a conversationId but haven't been synced yet.
  /// Used for startup recovery after app kill.
  List<Wal> getOrphanedWals() {
    return _wals
        .where(
          (w) =>
              w.status == WalStatus.miss &&
              w.storage == WalStorage.disk &&
              w.conversationId != null &&
              w.retryCount < 3,
        )
        .toList();
  }

  /// Persist retry metadata (retryCount, lastRetryAt) for a WAL after failed sync attempts.
  Future<void> persistRetryMetadata(Wal wal) async {
    await _saveWalsToFile();
  }

  /// Returns the approximate duration (in seconds) of UNSYNCED audio frames
  /// still in memory. Frames already delivered via WebSocket are excluded so
  /// the "Audio Saved Locally" indicator only appears when data is at risk.
  int getInFlightSeconds() {
    if (_framesPerSecond <= 0) return 0;
    int unsyncedCount = 0;
    for (int i = 0; i < _frameSynced.length; i++) {
      if (!_frameSynced[i]) unsyncedCount++;
    }
    return unsyncedCount ~/ _framesPerSecond;
  }

  @override
  Future<List<Wal>> getAllWals() async {
    return List.from(_wals);
  }

  @override
  Future<void> deleteAllSyncedWals() async {
    final syncedWals = _wals.where((w) => w.status == WalStatus.synced).toList();
    for (final wal in syncedWals) {
      await _deleteWal(wal);
    }
    await _saveWalsToFile();
    listener.onWalUpdated();
  }

  @override
  Future<void> deleteAllPendingWals() async {
    final pendingWals = _wals.where((w) => w.status == WalStatus.miss).toList();
    for (final wal in pendingWals) {
      await _deleteWal(wal);
    }
    await _saveWalsToFile();
    listener.onWalUpdated();
  }

  /// Removes terminally unavailable recordings when the user explicitly
  /// clears all local recordings. They are intentionally excluded from the
  /// retryable Pending action.
  @override
  Future<void> deleteAllCorruptedWals() async {
    final corruptedWals =
        _wals.where((w) => w.status == WalStatus.corrupted || w.status == WalStatus.outsideRecoveryWindow).toList();
    for (final wal in corruptedWals) {
      await _deleteWal(wal);
    }
    await _saveWalsToFile();
    listener.onWalUpdated();
  }

  @override
  void onFrameCaptured(WalFrame frame) {
    _frames.add(frame);
    _frameSynced.add(false);
  }

  @override
  void markFrameSynced(FrameSyncKey key) {
    for (int i = _frames.length - 1; i >= 0; i--) {
      if (_frames[i].syncKey == key) {
        _frameSynced[i] = true;
        break;
      }
    }
  }

  @override
  Future<SyncLocalFilesResponse?> syncAll({
    IWalSyncProgressListener? progress,
  }) =>
      _syncAll(progress: progress, includeBackfill: true);

  Future<SyncLocalFilesResponse?> syncFreshOnly({
    IWalSyncProgressListener? progress,
  }) =>
      _syncAll(progress: progress, includeBackfill: false);

  Future<AuthorizedRecoverySyncResult> syncAuthorizedRecovery({
    required String deviceId,
    required int targetWriteSeq,
    IWalSyncProgressListener? progress,
    int? nowSeconds,
  }) async {
    if (deviceId.isEmpty) {
      throw ArgumentError.value(deviceId, 'deviceId', 'must not be empty');
    }
    if (targetWriteSeq < 0) {
      throw ArgumentError.value(targetWriteSeq, 'targetWriteSeq', 'must not be negative');
    }
    final scope = _AuthorizedRecoveryScope(
      deviceId: deviceId,
      targetWriteSeq: targetWriteSeq,
    );
    final conversationBoundarySeconds = _conversationBoundarySeconds();
    await _syncMutex.acquire();
    try {
      final response = await _syncAllOwned(
        progress: progress,
        includeBackfill: false,
        authorizedRecovery: scope,
        nowSecondsOverride: nowSeconds,
        manualWal: null,
        conversationBoundarySecondsOverride: conversationBoundarySeconds,
      );
      return AuthorizedRecoverySyncResult(
        response: response,
        hasDeferredRecovery: _hasDeferredAuthorizedRecovery(
          scope,
          conversationBoundarySeconds: conversationBoundarySeconds,
        ),
      );
    } finally {
      _syncMutex.release();
    }
  }

  bool _hasDeferredAuthorizedRecovery(
    _AuthorizedRecoveryScope scope, {
    required int conversationBoundarySeconds,
  }) {
    final candidates = _wals
        .where(
          (wal) =>
              wal.storage == WalStorage.disk &&
              (wal.status == WalStatus.miss || wal.status == WalStatus.uploaded) &&
              _isAuthorizedHistoricalRecovery(wal, scope),
        )
        .toList();
    final permanentlyBlocked = _permanentlyBlockedLegacyRecoveryArtifacts(
      candidates.where((wal) => wal.status == WalStatus.miss).toList(),
      conversationBoundarySeconds: conversationBoundarySeconds,
    );
    return candidates.any(
      (wal) => wal.status == WalStatus.uploaded || !permanentlyBlocked.contains(wal),
    );
  }

  Set<String> _manualSyncWalIds(
    Wal selected, {
    required int conversationBoundarySeconds,
  }) {
    if (selected.conversationId != null || !_isRingRecoveryArtifact(selected)) {
      return {selected.id};
    }
    final groups = _continuousRingRecoveryGroups(
      _wals.where(
        (wal) =>
            wal.status == WalStatus.miss &&
            wal.storage == WalStorage.disk &&
            wal.conversationId == null &&
            _isRingRecoveryArtifact(wal),
      ),
      conversationBoundarySeconds: conversationBoundarySeconds,
    );
    final selectedGroup = groups.where(
      (group) => group.any((wal) => identical(wal, selected)),
    );
    return selectedGroup.isEmpty ? {selected.id} : selectedGroup.single.map((wal) => wal.id).toSet();
  }

  Future<SyncLocalFilesResponse?> _syncAll({
    IWalSyncProgressListener? progress,
    required bool includeBackfill,
  }) async {
    await _syncMutex.acquire();
    try {
      return await _syncAllOwned(
        progress: progress,
        includeBackfill: includeBackfill,
        authorizedRecovery: null,
        nowSecondsOverride: null,
        manualWal: null,
        conversationBoundarySecondsOverride: null,
      );
    } finally {
      _syncMutex.release();
    }
  }

  Future<SyncLocalFilesResponse?> _syncAllOwned({
    IWalSyncProgressListener? progress,
    required bool includeBackfill,
    required _AuthorizedRecoveryScope? authorizedRecovery,
    required int? nowSecondsOverride,
    required Wal? manualWal,
    required int? conversationBoundarySecondsOverride,
  }) async {
    int nowSeconds() => nowSecondsOverride ?? DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final conversationBoundarySeconds = conversationBoundarySecondsOverride ?? _conversationBoundarySeconds();

    await _flush();
    Wal? selectedManualWal = manualWal;
    if (manualWal != null) {
      final isTracked = _wals.any(
        (candidate) => identical(candidate, manualWal),
      );
      if (!isTracked) {
        DebugLogManager.logInfo(
          'Single WAL upload skipped — WAL no longer tracked',
          {'walId': manualWal.id},
        );
        return null;
      }
      if (_isUnassembledConversationRepair(manualWal)) {
        final conversationId = manualWal.conversationId!;
        final repairSources = _wals
            .where(
              (candidate) =>
                  candidate.conversationId == conversationId &&
                  _isRingRecoveryArtifact(candidate) &&
                  (candidate.status == WalStatus.miss || candidate.status == WalStatus.synced),
            )
            .toList();
        try {
          await _serializeWalAssembly(
            () => _compactRingConversation(
              conversationId,
              repairSources,
              conversationBoundarySeconds: conversationBoundarySeconds,
            ),
          );
          selectedManualWal = _wals.firstWhere(
            (candidate) =>
                candidate.conversationId == conversationId && candidate.sourceId?.startsWith('canonical_') == true,
          )..canonicalReplacement = true;
        } catch (error) {
          Logger.debug(
            'LocalWalSync: selected canonical repair remains local for $conversationId: $error',
          );
        }
      }
    } else {
      await prepareHistoricalRingFragments(
        nowSeconds: nowSeconds(),
        recoveryDeviceId: authorizedRecovery?.deviceId,
        recoverySequenceBoundary: authorizedRecovery?.targetWriteSeq,
        conversationBoundarySeconds: conversationBoundarySeconds,
      );
      await _repairBoundRingConversations(
        conversationBoundarySeconds: conversationBoundarySeconds,
      );
    }
    _isCancelled = false;
    _accumulatedResponse = null;

    final initialNowSeconds = nowSeconds();
    Wal? trackedManualWal;
    if (selectedManualWal != null) {
      for (final candidate in _wals) {
        if (identical(candidate, selectedManualWal)) {
          trackedManualWal = candidate;
          break;
        }
      }
    }
    if (selectedManualWal != null && trackedManualWal == null) {
      DebugLogManager.logInfo(
        'Single WAL upload skipped — WAL no longer tracked',
        {'walId': selectedManualWal.id},
      );
      return null;
    }
    final manualWalIds = trackedManualWal == null
        ? null
        : _manualSyncWalIds(
            trackedManualWal,
            conversationBoundarySeconds: conversationBoundarySeconds,
          );
    var wals = _wals
        .where(
          (wal) =>
              wal.status == WalStatus.miss &&
              wal.storage == WalStorage.disk &&
              (manualWalIds?.contains(wal.id) ??
                  _isEligibleForDrain(
                    wal,
                    nowSeconds: initialNowSeconds,
                    includeBackfill: includeBackfill,
                    authorizedRecovery: authorizedRecovery,
                  )),
        )
        .toList();
    if (wals.isEmpty) {
      Logger.debug("All synced!");
      DebugLogManager.logInfo('Local upload: no files to sync');
      return null;
    }

    if (SyncRateLimiter.instance.isLimited) {
      Logger.debug('Local upload: rate-limited until ${SyncRateLimiter.instance.until}, skipping');
      DebugLogManager.logEvent('local_upload_rate_limited', {'until': '${SyncRateLimiter.instance.until}'});
      return null;
    }

    DebugLogManager.logEvent('local_upload_started', {'walCount': wals.length});

    var resp = SyncLocalFilesResponse(
      newConversationIds: [],
      updatedConversationIds: [],
    );
    _accumulatedResponse = resp;

    int batchesCompleted = 0;
    int batchesFailed = 0;
    int corruptedCount = 0;
    int filesUploaded = 0;
    final totalFilesToUpload = wals.length;

    final attemptedWalIds = <String>{};
    final blockedLanes = <SyncUploadLane>{};
    final forcedBackfillConversationIds = <String>{};
    final unclaimableConversationIds = <String>{};
    final trackedManualConversationId = trackedManualWal?.conversationId;
    if (trackedManualConversationId != null) {
      final pendingConversationCount = _wals
          .where(
            (wal) => wal.status == WalStatus.miss && wal.conversationId == trackedManualConversationId,
          )
          .length;
      if (pendingConversationCount > (manualWalIds?.length ?? 0)) {
        forcedBackfillConversationIds.add(trackedManualConversationId);
      }
    }
    while (true) {
      // Re-snapshot between batches so a newly captured WAL can preempt an
      // hours-long historical drain without waiting for the original list.
      final batchNowSeconds = nowSeconds();
      final candidates = _wals
          .where(
            (wal) =>
                wal.status == WalStatus.miss &&
                wal.storage == WalStorage.disk &&
                !attemptedWalIds.contains(wal.id) &&
                (manualWalIds == null || manualWalIds.contains(wal.id)),
          )
          .toList();
      forcedBackfillConversationIds.addAll(
        oversizedFreshConversationIds(candidates, batchNowSeconds),
      );
      SyncUploadLane effectiveLane(Wal wal) =>
          wal.conversationId != null && forcedBackfillConversationIds.contains(wal.conversationId)
              ? SyncUploadLane.backfill
              : _syncLaneForWal(wal, batchNowSeconds);
      final pending = candidates
          .where(
            (wal) =>
                (manualWalIds != null ||
                    includeBackfill ||
                    effectiveLane(wal) == SyncUploadLane.fresh ||
                    _isAuthorizedHistoricalRecovery(wal, authorizedRecovery)) &&
                !blockedLanes.contains(effectiveLane(wal)),
          )
          .toList();
      if (pending.isEmpty) break;
      final batch = nextSyncUploadBatch(
        pending,
        batchNowSeconds,
        forcedBackfillConversationIds: forcedBackfillConversationIds,
        conversationBoundarySeconds: conversationBoundarySeconds,
      );
      if (batch.isEmpty) break;
      final coveredLegacyAliases = _legacyAliasesCoveredByBatch(
        pending,
        batch,
        conversationBoundarySeconds: conversationBoundarySeconds,
      );
      attemptedWalIds.addAll(batch.map((wal) => wal.id));
      final batchLane =
          batch.first.conversationId != null && forcedBackfillConversationIds.contains(batch.first.conversationId)
              ? SyncUploadLane.backfill
              : _syncLaneForWal(batch.first, batchNowSeconds);
      final batchConversationId = batch.first.conversationId;
      final claimLiveCapture = batchLane == SyncUploadLane.fresh &&
          !unclaimableConversationIds.contains(batchConversationId) &&
          canClaimLiveCapture(
            batch,
            candidates.where((wal) => wal.conversationId == batchConversationId).toList(),
            batchNowSeconds,
          );
      if (!claimLiveCapture && batchConversationId != null) {
        unclaimableConversationIds.add(batchConversationId);
      }
      if (_isCancelled) {
        Logger.debug("LocalWalSync: Upload cancelled");
        DebugLogManager.logWarning('Local upload cancelled', {
          'batchesUploaded': batchesCompleted,
          'batchesFailed': batchesFailed,
          'walsRemaining': wals.where((w) => w.status == WalStatus.miss).length,
        });
        // Clear the transient syncing flag on WALs not yet uploaded. Do NOT
        // touch status: any WAL already marked `uploaded` is safe on the
        // server and the reconciler will finish it — reverting it here would
        // cause a needless re-upload.
        for (final w in wals) {
          if (w.status != WalStatus.uploaded) {
            w.isSyncing = false;
            w.syncStartedAt = null;
            w.syncEtaSeconds = null;
          }
        }
        await _saveWalsToFile();
        listener.onWalUpdated();
        break;
      }
      List<File> files = [];
      List<Wal> batchWals = [];
      for (final wal in batch) {
        Logger.debug("sync id ${wal.id} ${wal.timerStart}");
        if (wal.filePath == null) {
          Logger.debug("file path is not found. wal id ${wal.id}");
          wal.markCorrupted();
          corruptedCount++;
          DebugLogManager.logWarning('WAL corrupted: file path missing', {
            'walId': wal.id,
          });
          continue;
        }

        final fullPath = await Wal.getFilePath(wal.filePath);
        Logger.debug("sync wal: ${wal.id} file: $fullPath");

        try {
          if (fullPath == null) {
            Logger.debug("could not construct file path for wal id ${wal.id}");
            wal.markCorrupted();
            corruptedCount++;
            DebugLogManager.logWarning('WAL corrupted: cannot construct path', {
              'walId': wal.id,
            });
            continue;
          }

          File file = File(fullPath);
          if (!file.existsSync()) {
            Logger.debug("file $fullPath does not exist");
            wal.markCorrupted();
            corruptedCount++;
            DebugLogManager.logWarning(
              'WAL corrupted: file not found on disk',
              {'walId': wal.id, 'filePath': wal.filePath ?? ''},
            );
            continue;
          }
          files.add(file);
          wal.isSyncing = true;
          batchWals.add(wal);
        } catch (e) {
          wal.markCorrupted();
          corruptedCount++;
          Logger.debug(e.toString());
          DebugLogManager.logError(
            e,
            null,
            'WAL corrupted: unexpected error - ${e.toString()}',
            {'walId': wal.id},
          );
        }
      }

      if (batchWals.length != batch.length) {
        // A logical recovery transaction is all-or-nothing. Uploading the
        // surviving subset would turn a missing local file into a permanent
        // transcript hole and could incorrectly retire overlapping legacy
        // aliases.
        for (final wal in batchWals) {
          wal.isSyncing = false;
        }
        await _saveWalsToFile();
        listener.onWalUpdated();
        continue;
      }

      // Report file-count progress
      progress?.onWalSyncedProgress(
        filesUploaded / totalFilesToUpload,
        phase: SyncPhase.uploadingToCloud,
        currentFile: filesUploaded,
        totalFiles: totalFilesToUpload,
      );

      listener.onWalUpdated();
      _PreparedUploadFiles? preparedUpload;
      try {
        preparedUpload = await _prepareUploadFiles(batchWals, files);
        DebugLogManager.logEvent('local_upload_prepared', {
          'sourceWalCount': batchWals.length,
          'uploadArtifactCount': preparedUpload.files.length,
        });
        // Upload only — return as soon as the server acknowledges. We do NOT
        // wait for server-side processing here; the reconciler resolves the
        // job_id later. Only WALs that actually became files (batchWals) are
        // mutated — corrupted ones already short-circuited above.
        final result = await _uploadGate.upload(
          preparedUpload.files,
          lane: batchLane,
          conversationId: batchWals.first.conversationId,
          claimLiveCapture: claimLiveCapture,
          replaceTranscript: batchWals.first.canonicalReplacement,
        );

        if (result.completed != null) {
          // 200 fast-path: server processed synchronously and returned a result.
          final r = result.completed!;
          resp.newConversationIds.addAll(
            r.newConversationIds.where(
              (id) => !resp.newConversationIds.contains(id),
            ),
          );
          resp.updatedConversationIds.addAll(
            r.updatedConversationIds.where(
              (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
            ),
          );
          for (final wal in [...batchWals, ...coveredLegacyAliases]) {
            wal.status = WalStatus.synced;
            wal.isSyncing = false;
            wal.syncStartedAt = null;
            wal.syncEtaSeconds = null;
            listener.onWalSynced(wal);
          }
        } else {
          // 202: audio safely received; processing in the background. Stamp the
          // shared job_id and mark uploaded. The reconciler resolves this to
          // synced / miss(retry) / corrupted out of the critical path. The
          // local file is retained until confirmed synced.
          final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
          for (final wal in [...batchWals, ...coveredLegacyAliases]) {
            wal.status = WalStatus.uploaded;
            wal.jobId = result.jobId;
            wal.uploadedAt = now;
            wal.isSyncing = false;
            wal.syncStartedAt = null;
            wal.syncEtaSeconds = null;
          }
          listener.onWalUpdated();
        }

        batchesCompleted++;
        // Count WALs no longer needing upload (uploaded or already synced).
        filesUploaded = wals
            .where(
              (w) => w.status == WalStatus.uploaded || w.status == WalStatus.synced,
            )
            .length;
      } on SyncRateLimitedException {
        // Pause only this lane. The other lane remains eligible in this drain.
        DebugLogManager.logEvent('local_upload_rate_limited', {
          'until': '${SyncRateLimiter.instance.until}',
        });
        blockedLanes.add(batchLane);
        for (final wal in batchWals) {
          wal.isSyncing = false;
          wal.syncStartedAt = null;
          wal.syncEtaSeconds = null;
        }
        await _saveWalsToFile();
        listener.onWalUpdated();
        continue;
      } on SyncRecoveryWindowExceededException {
        // Clear the in-flight flag on the whole batch first: the members the
        // rejection does NOT prove too old stay `miss` and must not be left
        // rendering as an upload that never finishes.
        for (final wal in batchWals) {
          wal.isSyncing = false;
          wal.syncStartedAt = null;
          wal.syncEtaSeconds = null;
        }
        final retired = _retireOutsideRecoveryWindow(batchWals);
        DebugLogManager.logEvent('local_upload_outside_recovery_window', {
          'batchWalIds': batchWals.map((w) => w.id).toList(),
          'retiredWalIds': retired.map((w) => w.id).toList(),
        });
        await _saveWalsToFile();
        listener.onWalUpdated();
        continue;
      } catch (e) {
        Logger.debug(
          'Local WAL upload batch failed: $e, pausing ${batchLane.name} lane',
        );
        batchesFailed++;
        // A transport/backend failure applies to the lane, not just the
        // current files. Walking every pending batch while offline turns a
        // large durable backlog into a tight network, CPU, and battery storm.
        // Keep every WAL retryable and let the connectivity/cooldown
        // coordinator wake a later drain.
        blockedLanes.add(batchLane);
        DebugLogManager.logError(
          e,
          null,
          'Local upload batch failed: ${e.toString()}',
          {
            'batchIndex': batchesCompleted + batchesFailed,
            'filesInBatch': files.length,
          },
        );
        // Upload failed: clear the transient flag, leave status `miss` so the
        // batch is retried on the next sync.
        for (final wal in batchWals) {
          wal.isSyncing = false;
          wal.syncStartedAt = null;
          wal.syncEtaSeconds = null;
        }
        if (manualWal != null) rethrow;
      } finally {
        if (preparedUpload != null) {
          await _deleteTemporaryUploadFiles(preparedUpload.temporaryFiles);
        }
      }

      await _saveWalsToFile();
      listener.onWalUpdated();
    }

    DebugLogManager.logEvent('local_upload_finished', {
      'batchesUploaded': batchesCompleted,
      'batchesFailed': batchesFailed,
      'corrupted': corruptedCount,
      'newConversations': resp.newConversationIds.length,
      'updatedConversations': resp.updatedConversationIds.length,
    });

    resp.localUploadFailures = batchesFailed;
    progress?.onWalSyncedProgress(1.0);
    return resp;
  }

  Future<void> _repairBoundRingConversations({
    required int conversationBoundarySeconds,
  }) =>
      _serializeWalAssembly(
        () => _repairBoundRingConversationsOwned(
          conversationBoundarySeconds: conversationBoundarySeconds,
        ),
      );

  Future<void> _repairBoundRingConversationsOwned({
    required int conversationBoundarySeconds,
  }) async {
    final sourcesByConversation = <String, List<Wal>>{};
    final existingCanonicalOwners = <String>{};
    for (final wal in _wals) {
      final conversationId = wal.conversationId;
      if (conversationId == null) continue;
      if (wal.sourceId?.startsWith('canonical_') == true) {
        existingCanonicalOwners.add(conversationId);
      } else if (wal.originalStorage == WalStorage.sdcard &&
          RingProtocol.parseRecoverySourceRange(wal.sourceId) != null) {
        sourcesByConversation.putIfAbsent(conversationId, () => []).add(wal);
      }
    }
    for (final entry in sourcesByConversation.entries) {
      if (existingCanonicalOwners.contains(entry.key)) continue;
      try {
        await _compactRingConversation(
          entry.key,
          entry.value,
          conversationBoundarySeconds: conversationBoundarySeconds,
        );
      } catch (error) {
        Logger.debug(
          'LocalWalSync: canonical repair remains local for ${entry.key}: $error',
        );
      }
    }
  }

  @override
  Future<SyncLocalFilesResponse?> syncWal({
    required Wal wal,
    IWalSyncProgressListener? progress,
  }) async {
    await _syncMutex.acquire();
    try {
      return await _syncAllOwned(
        progress: progress,
        includeBackfill: false,
        authorizedRecovery: null,
        nowSecondsOverride: null,
        manualWal: wal,
        conversationBoundarySecondsOverride: null,
      );
    } finally {
      _syncMutex.release();
    }
  }

  /// Retires the recordings a `backfill_lookback_exceeded` rejection proves the
  /// server will never accept, and only those.
  ///
  /// The backend decides the lookback from the OLDEST capture in the upload
  /// (`classify_sync_lane` measures `now - oldest_capture_at`), so a rejection
  /// only proves that one recording is outside the window — a batch mixes ages,
  /// and retiring all of it would strand recordings the server would still take.
  /// Everything captured no later than the proven-too-old one is necessarily
  /// outside the window as well, so the whole tail retires in one pass instead
  /// of costing another doomed upload per recording. The rest of the batch stays
  /// `miss` and re-forms into a batch without the poison on the next drain.
  List<Wal> _retireOutsideRecoveryWindow(List<Wal> rejectedBatch) {
    if (rejectedBatch.isEmpty) return const [];
    final provenTooOld = rejectedBatch.map((w) => w.timerStart).reduce(min);
    final retired = _wals
        .where((w) => w.status == WalStatus.miss && w.storage == WalStorage.disk && w.timerStart <= provenTooOld)
        .toList();
    for (final wal in retired) {
      wal.markOutsideRecoveryWindow();
    }
    return retired;
  }

  Future<bool> _localFileExists(Wal wal) async {
    if (wal.filePath == null) return false;
    final p = await Wal.getFilePath(wal.filePath);
    if (p == null) return false;
    return File(p).existsSync();
  }

  /// Resolve WALs sitting in [WalStatus.uploaded] by polling their server job
  /// — out of the upload critical path. Returns the new/updated conversation
  /// ids from jobs that reached a terminal state this pass so the caller can
  /// surface them to the UI.
  ///
  /// Idempotent and safe to run repeatedly and concurrently with an upload:
  /// it only touches `uploaded` WALs, and the upload loop only ever touches
  /// `miss` WALs, so the two never contend for the same recording. WALs are
  /// grouped by their shared `jobId` (batched upload → one job : N WALs).
  Future<SyncLocalFilesResponse> reconcileUploadedWals() async {
    final resp = SyncLocalFilesResponse(
      newConversationIds: [],
      updatedConversationIds: [],
    );

    final byJob = <String, List<Wal>>{};
    for (final w in _wals) {
      if (w.status == WalStatus.uploaded && w.jobId != null && w.jobId!.isNotEmpty) {
        byJob.putIfAbsent(w.jobId!, () => []).add(w);
      }
    }
    if (byJob.isEmpty) return resp;

    bool changed = false;
    final nowSecs = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    const maxConcurrent = 3;
    final entries = byJob.entries.toList();

    for (var i = 0; i < entries.length; i += maxConcurrent) {
      final slice = entries.sublist(i, min(i + maxConcurrent, entries.length));
      final fetched = await Future.wait(
        slice.map((e) async => (e.value, await _syncJobStatusFetcher(e.key))),
      );
      var transientFailureSeen = false;

      for (final (members, fetch) in fetched) {
        final jobId = members.first.jobId;
        final memberWalIds = members.map((w) => w.id).toList();
        switch (fetch.outcome) {
          case SyncJobFetchOutcome.transient:
            // Network/5xx — leave as `uploaded`, retry on the next pass.
            transientFailureSeen = true;
            DebugLogManager.logEvent('reconcile_poll', {
              'jobId': jobId,
              'memberWalIds': memberWalIds,
              'outcome': 'transient',
            });
            break;
          case SyncJobFetchOutcome.notFound:
            // Job expired or unknown. Recover from the retained local file.
            for (final w in members) {
              changed = true;
              final hadJob = w.jobId;
              w.jobId = null;
              final fileExists = await _localFileExists(w);
              if (fileExists) {
                w.status = WalStatus.miss; // re-upload next sync (dedup-safe)
                w.retryCount += 1;
                w.lastRetryAt = nowSecs;
              } else {
                w.markCorrupted(); // nothing left to recover
              }
              DebugLogManager.logEvent('reconcile_revert', {
                'walId': w.id,
                'jobId': hadJob,
                'outcome': 'not_found',
                'fileExists': fileExists,
                'newStatus': w.status.name,
                'retryCount': w.retryCount,
              });
            }
            break;
          case SyncJobFetchOutcome.ok:
            final s = fetch.status!;
            final terminalPolicy = syncJobTerminalPolicy(
              status: s.status,
              isTerminal: s.isTerminal,
            );
            if (terminalPolicy == SyncJobTerminalPolicy.wait) {
              DebugLogManager.logEvent('reconcile_poll', {
                'jobId': jobId,
                'memberWalIds': memberWalIds,
                'outcome': 'non_terminal',
                'serverStatus': s.status,
                'processedSegments': s.processedSegments,
                'totalSegments': s.totalSegments,
              });
              break; // still queued/processing — check later
            }
            if (s.result != null) {
              resp.newConversationIds.addAll(
                s.result!.newConversationIds.where(
                  (id) => !resp.newConversationIds.contains(id),
                ),
              );
              resp.updatedConversationIds.addAll(
                s.result!.updatedConversationIds.where(
                  (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
                ),
              );
            }
            if (terminalPolicy == SyncJobTerminalPolicy.acknowledge) {
              DebugLogManager.logEvent('reconcile_poll', {
                'jobId': jobId,
                'memberWalIds': memberWalIds,
                'outcome': 'completed',
                'newConversations': s.result?.newConversationIds.length ?? 0,
                'updatedConversations': s.result?.updatedConversationIds.length ?? 0,
              });
              for (final w in members) {
                changed = true;
                w.status = WalStatus.synced;
                w.jobId = null;
                listener.onWalSynced(w);
              }
            } else {
              // status='failed' with totalSegments==0 can only come from the
              // backend stale guard (mark_job_completed only sets 'failed'
              // when total>0). String hint is a fallback if the structural
              // signal ever becomes ambiguous.
              final capacityLimited =
                  syncJobIsBackendBusy(s) || s.reasonCode == 'backfill_paced' || s.reasonCode == 'backfill_capacity';
              if (capacityLimited) {
                SyncRateLimiter.instance.markLimited(
                  retryAfterSeconds: s.retryAfter ?? 600,
                  reason: RateLimitReason.backendBusy,
                );
              }
              for (final w in members) {
                changed = true;
                final hadJob = w.jobId;
                w.status = WalStatus.miss;
                w.jobId = null;
                if (!capacityLimited) {
                  w.retryCount += 1;
                  w.lastRetryAt = nowSecs;
                }
                DebugLogManager.logEvent('reconcile_revert', {
                  'walId': w.id,
                  'jobId': hadJob,
                  'outcome': s.status,
                  'serverError': s.error,
                  'failedSegments': s.failedSegments,
                  'totalSegments': s.totalSegments,
                  'retryCount': w.retryCount,
                  'capacityLimited': capacityLimited,
                  'retryCountBumped': !capacityLimited,
                });
              }
            }
            break;
        }
      }
      if (transientFailureSeen) {
        // One unavailable fetch is enough evidence to stop this pass. With a
        // large uploaded backlog, probing every job while offline created
        // hundreds of doomed requests per wake. At most the bounded
        // concurrent slice is attempted; all remaining jobs stay durable.
        break;
      }
    }

    if (changed) {
      await _saveWalsToFile();
      listener.onWalUpdated();
    }
    return resp;
  }
}
