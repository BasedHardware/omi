import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:crypto/crypto.dart';
import 'package:uuid/uuid.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/wals/batch_ring_proof.dart';
import 'package:omi/services/wals/ring_drain_policy.dart';
export 'package:omi/services/wals/ring_drain_policy.dart' show ringDrainRecoveryEnabled;

import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/wal_file_manager.dart';

class CustodyWalRef {
  final String fileName;
  final int bytes;
  final int frames;

  final int? liveRingId;
  final int? liveOrdinalStart;
  final int? liveOrdinalEnd;
  final String? batchLiveSession;
  final String? liveDeviceId;
  final String? ownerUid;
  final String? fileSha256;
  final int? downloadRingId;
  final int? downloadSeqStart;
  final int? downloadSeqEnd;
  final String? downloadDeviceId;

  const CustodyWalRef({
    required this.fileName,
    required this.bytes,
    required this.frames,
    this.liveRingId,
    this.liveOrdinalStart,
    this.liveOrdinalEnd,
    this.batchLiveSession,
    this.liveDeviceId,
    this.ownerUid,
    this.fileSha256,
    this.downloadRingId,
    this.downloadSeqStart,
    this.downloadSeqEnd,
    this.downloadDeviceId,
  });

  Map<String, dynamic> toJson() => {
        'file': fileName,
        'bytes': bytes,
        'frames': frames,
        if (liveRingId != null) 'live_ring': liveRingId,
        if (liveOrdinalStart != null) 'live_start': liveOrdinalStart,
        if (liveOrdinalEnd != null) 'live_end': liveOrdinalEnd,
        if (batchLiveSession != null) 'batch_session': batchLiveSession,
        if (liveDeviceId != null) 'live_device': liveDeviceId,
        if (ownerUid != null) 'owner': ownerUid,
        if (fileSha256 != null) 'sha256': fileSha256,
        if (downloadRingId != null) 'download_ring': downloadRingId,
        if (downloadSeqStart != null) 'download_start': downloadSeqStart,
        if (downloadSeqEnd != null) 'download_end': downloadSeqEnd,
        if (downloadDeviceId != null) 'download_device': downloadDeviceId,
      };

  static CustodyWalRef? fromJson(Object? json) {
    if (json is! Map) return null;
    final file = json['file'], bytes = json['bytes'], frames = json['frames'];
    if (file is! String || bytes is! int || frames is! int) return null;
    if (json.containsKey('download_ring') &&
        (json['download_ring'] is! int ||
            json['download_start'] is! int ||
            json['download_end'] is! int ||
            json['download_device'] is! String)) {
      return null;
    }
    int? asInt(Object? v) => v is int ? v : null;
    return CustodyWalRef(
      fileName: file,
      bytes: bytes,
      frames: frames,
      liveRingId: asInt(json['live_ring']),
      liveOrdinalStart: asInt(json['live_start']),
      liveOrdinalEnd: asInt(json['live_end']),
      batchLiveSession: json['batch_session'] as String?,
      liveDeviceId: json['live_device'] as String?,
      ownerUid: json['owner'] as String?,
      fileSha256: json['sha256'] as String?,
      downloadRingId: asInt(json['download_ring']),
      downloadSeqStart: asInt(json['download_start']),
      downloadSeqEnd: asInt(json['download_end']),
      downloadDeviceId: json['download_device'] as String?,
    );
  }
}

typedef _LiveMark = ({int ringSeq, int liveIndex, int ordinalBoundary});
typedef _LiveChunk = ({int start, int end, CustodyWalRef wal});

/// Persisted mappings are not custody: only validated disk/index references
/// can fill their ordinal intervals. Session IDs prevent reconnect aliasing.
class _BatchLiveSession {
  _BatchLiveSession(this.id);
  final String id;
  final List<_LiveMark> marks = [];
  final List<_LiveChunk> chunks = [];

  Map<String, dynamic> toJson() => {
        'id': id,
        'marks': [
          for (final m in marks) [m.ringSeq, m.liveIndex, m.ordinalBoundary]
        ],
        'chunks': [for (final c in chunks) c.wal.toJson()],
      };

  static _BatchLiveSession? fromJson(Object? json) {
    if (json is! Map || json['id'] is! String || (json['id'] as String).isEmpty) return null;
    final session = _BatchLiveSession(json['id']);
    final marks = json['marks'], chunks = json['chunks'];
    if (marks is! List || chunks is! List || marks.length > 4096 || chunks.length > 4096) return null;
    for (final m in marks) {
      if (m is! List || m.length != 3 || m.any((v) => v is! int)) return null;
      final mark = (ringSeq: m[0] as int, liveIndex: m[1] as int, ordinalBoundary: m[2] as int);
      if (mark.ringSeq < 0 || mark.ordinalBoundary < 0 || mark.liveIndex < 0 || mark.liveIndex > 0xFFFF) return null;
      if (session.marks.isNotEmpty &&
          (mark.ringSeq <= session.marks.last.ringSeq || mark.ordinalBoundary <= session.marks.last.ordinalBoundary)) {
        return null;
      }
      session.marks.add(mark);
    }
    for (final c in chunks) {
      final ref = CustodyWalRef.fromJson(c);
      if (ref == null ||
          ref.liveOrdinalStart == null ||
          ref.liveOrdinalEnd == null ||
          ref.liveOrdinalStart! < 0 ||
          ref.liveOrdinalEnd! <= ref.liveOrdinalStart!) {
        return null;
      }
      session.chunks.add((start: ref.liveOrdinalStart!, end: ref.liveOrdinalEnd!, wal: ref));
    }
    return session;
  }
}

class LiveRangeProof {
  final int startSeq;
  final int endSeq;
  final int startLiveOrdinal;
  final int endLiveOrdinal;
  final List<CustodyWalRef> wals;

  const LiveRangeProof({
    required this.startSeq,
    required this.endSeq,
    required this.startLiveOrdinal,
    required this.endLiveOrdinal,
    required this.wals,
  });

  Map<String, dynamic> toJson() => {
        'start_seq': startSeq,
        'end_seq': endSeq,
        'start_live': startLiveOrdinal,
        'end_live': endLiveOrdinal,
        'wals': wals.map((w) => w.toJson()).toList(),
      };

  static LiveRangeProof? fromJson(Object? json) {
    if (json is! Map) return null;
    final s = json['start_seq'], e = json['end_seq'], sl = json['start_live'], el = json['end_live'];
    final walsJson = json['wals'];
    if (s is! int || e is! int || sl is! int || el is! int || walsJson is! List) return null;
    if (e <= s || el <= sl) return null;
    final wals = walsJson.map(CustodyWalRef.fromJson).toList();
    if (wals.any((w) => w == null)) return null;
    return LiveRangeProof(
      startSeq: s,
      endSeq: e,
      startLiveOrdinal: sl,
      endLiveOrdinal: el,
      wals: wals.cast<CustodyWalRef>(),
    );
  }
}

class RingRangeProof {
  final int startSeq;
  final int endSeq;
  final List<CustodyWalRef> wals;

  const RingRangeProof({required this.startSeq, required this.endSeq, required this.wals});

  Map<String, dynamic> toJson() => {
        'start_seq': startSeq,
        'end_seq': endSeq,
        'wals': wals.map((w) => w.toJson()).toList(),
      };

  static RingRangeProof? fromJson(Object? json) {
    if (json is! Map) return null;
    final s = json['start_seq'], e = json['end_seq'];
    final walsJson = json['wals'];
    if (s is! int || e is! int || walsJson is! List || e <= s) return null;
    final wals = walsJson.map(CustodyWalRef.fromJson).toList();
    if (wals.any((w) => w == null)) return null;
    return RingRangeProof(startSeq: s, endSeq: e, wals: wals.cast<CustodyWalRef>());
  }
}

class RingCustodyCheckpoint {
  final String deviceId;

  int? ringId;

  int durableSeq;

  int lastAdvancedSeq;

  int? lastMarkSeq;
  int? lastMarkLiveIndex;

  int? lastAdvancedMarkSeq;

  final List<LiveRangeProof> liveRanges;
  final List<RingRangeProof> ringRanges;

  final Map<String, _BatchLiveSession> _batchSessions = {};

  int reportedReadSeq;

  int reportedWriteSeq;

  RingCustodyCheckpoint({
    required this.deviceId,
    this.ringId,
    this.durableSeq = 0,
    this.lastAdvancedSeq = 0,
    this.lastMarkSeq,
    this.lastMarkLiveIndex,
    this.lastAdvancedMarkSeq,
    List<LiveRangeProof>? liveRanges,
    List<RingRangeProof>? ringRanges,
    this.reportedReadSeq = 0,
    this.reportedWriteSeq = 0,
  })  : liveRanges = liveRanges ?? [],
        ringRanges = ringRanges ?? [];

  Map<String, dynamic> toJson() => {
        'device_id': deviceId,
        'ring_id': ringId,
        'durable_seq': durableSeq,
        'last_advanced_seq': lastAdvancedSeq,
        'last_durable_mark': lastMarkSeq,
        'last_durable_mark_live_index': lastMarkLiveIndex,
        'last_advanced_mark': lastAdvancedMarkSeq,
        'live_ranges': liveRanges.map((r) => r.toJson()).toList(),
        'ring_ranges': ringRanges.map((r) => r.toJson()).toList(),
        if (_batchSessions.isNotEmpty) 'batch_sessions': [for (final s in _batchSessions.values) s.toJson()],
        'reported_read_seq': reportedReadSeq,
        'reported_write_seq': reportedWriteSeq,
      };

  static RingCustodyCheckpoint? fromJson(Map<String, dynamic> json) {
    final deviceId = json['device_id'];
    if (deviceId is! String || deviceId.isEmpty) return null;
    int? asInt(Object? v) => v is int ? v : null;
    final liveRanges = <LiveRangeProof>[];
    final ringRanges = <RingRangeProof>[];
    for (final r in (json['live_ranges'] as List?) ?? const []) {
      final parsed = LiveRangeProof.fromJson(r);
      if (parsed == null) return null;
      liveRanges.add(parsed);
    }
    for (final r in (json['ring_ranges'] as List?) ?? const []) {
      final parsed = RingRangeProof.fromJson(r);
      if (parsed == null) return null;
      ringRanges.add(parsed);
    }
    final checkpoint = RingCustodyCheckpoint(
      deviceId: deviceId,
      ringId: asInt(json['ring_id']),
      durableSeq: asInt(json['durable_seq']) ?? 0,
      lastAdvancedSeq: asInt(json['last_advanced_seq']) ?? 0,
      lastMarkSeq: asInt(json['last_durable_mark']),
      lastMarkLiveIndex: asInt(json['last_durable_mark_live_index']),
      lastAdvancedMarkSeq: asInt(json['last_advanced_mark']),
      liveRanges: liveRanges,
      ringRanges: ringRanges,
      reportedReadSeq: asInt(json['reported_read_seq']) ?? 0,
      reportedWriteSeq: asInt(json['reported_write_seq']) ?? 0,
    );
    if (batchRingProofEnabled && json['batch_sessions'] is List) {
      for (final raw in (json['batch_sessions'] as List).take(64)) {
        final session = _BatchLiveSession.fromJson(raw);
        if (session != null) {
          checkpoint._batchSessions[session.id] = session;
        }
      }
    }
    return checkpoint;
  }
}

typedef CustodyWalValidator = Future<bool> Function(CustodyWalRef ref);
typedef CustodyWalValidatorSnapshot = Future<CustodyWalValidator> Function();

/// Reuses only a read's index rows. Successful file checks are never memoized.
class CustodyProofMemo {
  CustodyReadValidation? _validator;
}

Future<bool> walFileManagerCustodyValidator(CustodyWalRef ref) async {
  try {
    Wal? indexed;
    for (final wal in await WalFileManager.loadIndexedWals()) {
      final name = (wal.filePath ?? wal.getFileName()).split('/').last;
      if (name == ref.fileName) {
        indexed = wal;
        break;
      }
    }
    return _validateIndexedWal(ref, indexed);
  } catch (_) {
    return false;
  }
}

Future<bool> _validateIndexedWal(CustodyWalRef ref, Wal? indexed, {Future<String> Function(File)? fileDigest}) async {
  try {
    if (indexed == null || indexed.status == WalStatus.corrupted) return false;
    if (ref.ownerUid == null ||
        ref.ownerUid!.isEmpty ||
        ref.ownerUid == 'legacy' ||
        indexed.ownerUid != ref.ownerUid ||
        SharedPreferencesUtil().uid != ref.ownerUid) {
      return false;
    }
    if (ref.fileSha256 == null ||
        !RegExp(r'^[a-f0-9]{64}$').hasMatch(ref.fileSha256!) ||
        indexed.fileSha256 != ref.fileSha256) {
      return false;
    }
    if (ref.downloadRingId == null && ref.liveRingId == null) return false;
    if (ref.liveRingId != null &&
        (ref.liveDeviceId == null ||
            ref.liveDeviceId!.isEmpty ||
            indexed.liveDeviceId != ref.liveDeviceId ||
            (ref.batchLiveSession == null && indexed.device != ref.liveDeviceId) ||
            ref.liveOrdinalStart == null ||
            ref.liveOrdinalEnd == null ||
            ref.liveOrdinalEnd! <= ref.liveOrdinalStart!)) {
      return false;
    }
    if (indexed.storage != WalStorage.disk || indexed.totalFrames != ref.frames) return false;
    if (ref.ownerUid != null && (indexed.ownerUid != ref.ownerUid || SharedPreferencesUtil().uid != ref.ownerUid)) {
      return false;
    }
    if (ref.downloadRingId != null &&
        (!ringDrainRecoveryEnabled ||
            ref.ownerUid == null ||
            ref.ownerUid!.isEmpty ||
            ref.downloadDeviceId == null ||
            ref.downloadDeviceId!.isEmpty ||
            ref.downloadSeqStart == null ||
            ref.downloadSeqEnd == null ||
            ref.downloadSeqEnd! <= ref.downloadSeqStart! ||
            indexed.downloadFileBytes != ref.bytes ||
            indexed.downloadRingId != ref.downloadRingId ||
            indexed.downloadSeqStart != ref.downloadSeqStart ||
            indexed.downloadSeqEnd != ref.downloadSeqEnd ||
            indexed.device != ref.downloadDeviceId)) {
      return false;
    }
    if (ref.batchLiveSession != null &&
        (!batchRingProofEnabled ||
            indexed.batchLiveSession != ref.batchLiveSession ||
            indexed.liveDeviceId != ref.liveDeviceId ||
            ref.ownerUid == null ||
            ref.ownerUid!.isEmpty ||
            indexed.ownerUid != ref.ownerUid ||
            SharedPreferencesUtil().uid != ref.ownerUid)) {
      return false;
    }
    if (ref.liveRingId != null && indexed.liveRingId != ref.liveRingId) return false;
    if (ref.liveOrdinalStart != null && indexed.liveOrdinalStart != ref.liveOrdinalStart) return false;
    if (ref.liveOrdinalEnd != null && indexed.liveOrdinalEnd != ref.liveOrdinalEnd) return false;
    final path = await Wal.getFilePath(ref.fileName);
    if (path == null) return false;
    final file = File(path);
    if (!file.existsSync()) return false;
    final matches = (await file.length()) == ref.bytes;
    if (!matches ||
        (await (fileDigest?.call(file) ?? sha256.bind(file.openRead()).first.then((hash) => hash.toString()))) !=
            ref.fileSha256) {
      return false;
    }
    // Zero-frame proof is an explicit durable index row + canonical marker,
    // never the vacuous truth of an empty list of audio WALs.
    if (ref.frames == 0) {
      if (ref.downloadRingId == null || !ref.fileName.endsWith('.ring-empty')) return false;
      final marker = jsonDecode(await file.readAsString());
      if (marker is! Map ||
          marker['kind'] != 'empty_ring_records_v1' ||
          marker['device'] != ref.downloadDeviceId ||
          marker['ring'] != ref.downloadRingId ||
          marker['start'] != ref.downloadSeqStart ||
          marker['end'] != ref.downloadSeqEnd ||
          marker['owner'] != ref.ownerUid) {
        return false;
      }
    }
    return SharedPreferencesUtil().uid == ref.ownerUid;
  } catch (e) {
    Logger.debug('PendantRingCustody: WAL validation failed for ${ref.fileName}: $e');
    return false;
  }
}

class LivePacketOrdinals {
  int? _lastCounter;
  int _nextOrdinal = 0;
  bool _broken = false;

  bool get isBroken => _broken;
  int? get lastCounter => _lastCounter;
  int get nextOrdinal => _nextOrdinal;

  int? observe(int packetCounter, int fragmentIndex) {
    if (_broken) return null;
    if (fragmentIndex != 0) {
      _broken = true;
      return null;
    }
    final counter = packetCounter & 0xFFFF;
    final last = _lastCounter;
    if (last == null) {
      _lastCounter = counter;
      return _nextOrdinal++;
    }
    if (counter == ((last + 1) & 0xFFFF)) {
      _lastCounter = counter;
      return _nextOrdinal++;
    }
    _broken = true;
    return null;
  }

  int? ordinalBoundaryFor(int liveIndex) {
    if (_broken) return null;
    final last = _lastCounter;
    if (last == null) {
      return liveIndex == 0 ? 0 : null;
    }
    final idx = liveIndex & 0xFFFF;
    final fwd = (idx - last) & 0xFFFF;
    if (fwd > 0 && fwd < 0x8000) {
      return _nextOrdinal - 1 + fwd;
    }
    final back = (last - idx) & 0xFFFF;
    if (back <= _nextOrdinal - 1 && back < 0x8000) {
      return _nextOrdinal - 1 - back;
    }
    return null;
  }
}

class _DeviceCustody {
  int epoch = 0;
  String batchSessionId = const Uuid().v4();
  Object? sessionToken;
  RingCustodyCheckpoint checkpoint;
  bool liveEnabled = false;
  bool connected = false;

  bool incarnationInvalid = false;

  LivePacketOrdinals ordinals = LivePacketOrdinals();

  final List<_LiveMark> marks = [];

  int? liveAnchorSeq;
  final List<_LiveChunk> durableLiveChunks = [];
  final List<LiveRangeProof> releasedLiveRanges = [];
  static const int maxReleasedLiveRanges = 64;

  bool evidenceBroken = false;

  Future<int?> Function(int seq)? advanceCallback;

  Future<void> markTask = Future.value();

  _DeviceCustody(this.checkpoint);

  int get durableFrontier {
    var frontier = checkpoint.durableSeq;
    if (checkpoint.reportedReadSeq > frontier) frontier = checkpoint.reportedReadSeq;
    for (final r in checkpoint.ringRanges) {
      if (r.startSeq <= frontier && r.endSeq > frontier) frontier = r.endSeq;
    }
    for (final r in checkpoint.liveRanges) {
      if (r.startSeq <= frontier && r.endSeq > frontier) frontier = r.endSeq;
    }
    return frontier;
  }
}

typedef LiveFrameObservation = int?;

/// One read's index authority, never a cache of successful file hashes.
/// An unrelated index mutation revokes it; only the read's own durable write
/// obtains a replacement snapshot. Account/session fences remain independent.
class CustodyReadValidation {
  final CustodyWalValidator _validate;
  final bool Function() _current;
  CustodyReadValidation(this._validate, this._current);
  bool get isCurrent => _current();
  Future<bool> call(CustodyWalRef ref) async => isCurrent && await _validate(ref) && isCurrent;
}

class PendantRingCustody {
  final Map<String, _DeviceCustody> _devices = {};
  final PendantCustodyStore _store;
  final CustodyWalValidator _walValidator;
  final CustodyWalValidatorSnapshot? _customSnapshot;
  final Future<List<Wal>> Function() _indexLoader;
  final Future<String> Function(File)? _fileDigest;

  Future<void> _saveQueue = Future.value();

  PendantRingCustody(
      {PendantCustodyStore? store,
      CustodyWalValidator? walValidator,
      CustodyWalValidatorSnapshot? walValidatorSnapshot,
      Future<List<Wal>> Function()? indexLoader,
      Future<String> Function(File)? fileDigest})
      : _store = store ?? PendantCustodyStore(),
        _customSnapshot = walValidatorSnapshot,
        _indexLoader = indexLoader ?? WalFileManager.loadIndexedWals,
        _fileDigest = fileDigest,
        _walValidator = walValidator ?? walFileManagerCustodyValidator;

  static final PendantRingCustody shared = PendantRingCustody();

  Future<CustodyWalValidator> _validationSnapshot() async {
    if (_customSnapshot != null) return _customSnapshot!();
    if (!ringDrainRecoveryEnabled || _walValidator != walFileManagerCustodyValidator) return _walValidator;
    try {
      // One persisted index snapshot per operation, or per owned READ.
      // Only index rows are reused; file bytes are hashed on every decision.
      final indexed = <String, Wal>{
        for (final wal in await _indexLoader()) (wal.filePath ?? wal.getFileName()).split('/').last as String: wal,
      };
      return (ref) => _validateIndexedWal(ref, indexed[ref.fileName], fileDigest: _fileDigest);
    } catch (_) {
      return (_) async => false;
    }
  }

  Future<CustodyReadValidation> createReadValidator() async {
    final revision = WalFileManager.indexRevision;
    final validate = await _validationSnapshot();
    return CustodyReadValidation(validate, () => _customValidation || revision == WalFileManager.indexRevision);
  }

  /// Constant work per connected device, independent of the ledger's size.
  /// Live notification diagnostics must not sort/copy all historical ranges.
  Map<String, Map<String, Object?>> get diagnosticMarkStateByDevice => Map.unmodifiable({
        for (final entry in _devices.entries)
          entry.key: Map<String, Object?>.unmodifiable({
            'ring_id': entry.value.checkpoint.ringId,
            'evidence_broken': entry.value.evidenceBroken,
            'incarnation_invalid': entry.value.incarnationInvalid,
            'last_observed_mark_seq': entry.value.marks.lastOrNull?.ringSeq,
            'last_observed_mark_index': entry.value.marks.lastOrNull?.liveIndex,
          }),
      });

  /// Content-free ledger metadata only. Export never validates or advances.
  /// Keep this getter separate from custody decisions (Q12-AC diagnostics).
  Map<String, Map<String, Object?>> get diagnosticsByDevice => Map.unmodifiable({
        for (final entry in _devices.entries)
          entry.key: (() {
            final s = entry.value;
            final cp = s.checkpoint;
            final ranges = [
              for (final r in cp.ringRanges) (r.startSeq, r.endSeq),
              for (final r in cp.liveRanges) (r.startSeq, r.endSeq),
            ]..sort((a, b) => a.$1.compareTo(b.$1));
            var span = 0, start = -1, end = -1;
            var frontier = cp.reportedReadSeq > cp.durableSeq ? cp.reportedReadSeq : cp.durableSeq;
            for (final r in ranges) {
              if (r.$1 <= frontier && r.$2 > frontier) frontier = r.$2;
              if (r.$2 <= r.$1) continue;
              if (start < 0 || r.$1 > end) {
                if (start >= 0) span += end - start;
                start = r.$1;
                end = r.$2;
              } else if (r.$2 > end) {
                end = r.$2;
              }
            }
            if (start >= 0) span += end - start;
            var gapEnd = cp.reportedWriteSeq;
            for (final r in ranges) {
              if (r.$1 > frontier && r.$1 < gapEnd) gapEnd = r.$1;
            }
            final gap = (gapEnd - frontier).clamp(0, 1 << 62);
            return Map<String, Object?>.unmodifiable({
              'connection_epoch': s.epoch,
              'connected': s.connected,
              'live_enabled': s.liveEnabled,
              'ring_id': cp.ringId,
              'read_seq': cp.reportedReadSeq,
              'write_seq': cp.reportedWriteSeq,
              'durable_frontier': frontier,
              'last_advanced_seq': cp.lastAdvancedSeq,
              'last_mark_seq': cp.lastMarkSeq,
              'last_advanced_mark_seq': cp.lastAdvancedMarkSeq,
              'evidence_broken': s.evidenceBroken,
              'incarnation_invalid': s.incarnationInvalid,
              'pending_marks': s.marks.length,
              'last_observed_mark_seq': s.marks.lastOrNull?.ringSeq,
              'last_observed_mark_index': s.marks.lastOrNull?.liveIndex,
              'proof_range_count': ranges.length,
              'proof_record_span': span,
              'batch_proof_ranges':
                  cp.liveRanges.where((r) => r.wals.any((w) => w.fileName.startsWith('audio_omimobilebatch'))).length,
              'first_unproven_start': gap > 0 ? frontier : null,
              'first_unproven_length': gap,
              'records_held_behind_gap': gap > 0 ? (cp.reportedWriteSeq - gapEnd).clamp(0, 1 << 62) : 0,
            });
          })(),
      });

  _DeviceCustody? _state(String deviceId, int epoch) {
    final s = _devices[deviceId];
    return (s != null && s.epoch == epoch) ? s : null;
  }

  bool _isSession(_DeviceCustody state, String deviceId, int epoch, Object sessionToken) =>
      identical(_devices[deviceId], state) &&
      state.epoch == epoch &&
      identical(state.sessionToken, sessionToken) &&
      state.connected;

  Future<void> beginConnection(
    String deviceId,
    int epoch,
    RingInfo info, {
    Object? sessionToken,
    int? effectiveCaps,
    Future<int?> Function(int seq)? replayAdvance,
    Future<int?> Function(int seq)? onAdvanceReady,
  }) async {
    final token = sessionToken ?? Object();
    final existing = _devices[deviceId];
    final _DeviceCustody state;
    if (existing != null && existing.epoch == epoch && identical(existing.sessionToken, token)) {
      state = existing;
      state.marks.clear();
      state.liveAnchorSeq = null;
      state.releasedLiveRanges.clear();
      state.durableLiveChunks.clear();
      state.evidenceBroken = false;
      state.ordinals = LivePacketOrdinals();
    } else {
      state = _DeviceCustody(RingCustodyCheckpoint(deviceId: deviceId))
        ..epoch = epoch
        ..sessionToken = token;
      _devices[deviceId] = state;
    }
    state.batchSessionId = const Uuid().v4();
    state.connected = true;
    state.advanceCallback = onAdvanceReady ?? replayAdvance;
    state.marks.clear();
    state.liveAnchorSeq = null;
    state.releasedLiveRanges.clear();
    state.durableLiveChunks.clear();
    state.evidenceBroken = false;
    state.incarnationInvalid = false;
    state.ordinals = LivePacketOrdinals();

    final caps = effectiveCaps ?? info.effectiveCaps;
    final ringId = (caps & RingProtocol.capRingId) != 0 ? info.ringId : null;

    if (ringId != null) {
      await _saveQueue;
      final persisted = await _store.load(deviceId);
      if (!_isSession(state, deviceId, epoch, token)) return;
      if (ringDrainRecoveryEnabled && persisted?.ringId == ringId) {
        persisted!.reportedReadSeq = info.readSeq;
        persisted.lastAdvancedSeq = info.readSeq;
      }
      final valid = persisted != null && persisted.ringId == ringId && await _validateCheckpoint(persisted);
      if (!_isSession(state, deviceId, epoch, token)) return;
      if (valid) {
        state.checkpoint = persisted;
      } else if (persisted != null && persisted.ringId != ringId) {
        Logger.debug('PendantRingCustody: ring incarnation changed for $deviceId, discarding stale checkpoint');
        state.checkpoint = RingCustodyCheckpoint(deviceId: deviceId);
      } else if (persisted != null) {
        Logger.debug('PendantRingCustody: checkpoint for $deviceId failed validation, discarding');
        state.checkpoint = RingCustodyCheckpoint(deviceId: deviceId);
      }
      state.checkpoint.ringId = ringId;
    } else {
      state.checkpoint.ringId = null;
    }
    state.checkpoint.reportedReadSeq = info.readSeq;
    state.checkpoint.reportedWriteSeq = info.writeSeq;
    if (ringDrainRecoveryEnabled) state.checkpoint.lastAdvancedSeq = info.readSeq;
    if (info.readSeq > state.checkpoint.durableSeq) state.checkpoint.durableSeq = info.readSeq;

    if (ringDrainRecoveryEnabled && ringId != null) {
      await restoreDownloadedRanges(deviceId, epoch, ringId, reportedReadSeq: info.readSeq);
      if (!_isSession(state, deviceId, epoch, token)) return;
    }

    if (batchRingProofEnabled && ringId != null && state.checkpoint._batchSessions.isNotEmpty) {
      await _restoreBatchProofs(state, deviceId, epoch, token);
      if (!_isSession(state, deviceId, epoch, token)) return;
    }

    final frontier = ringDrainRecoveryEnabled
        ? (await validatedAdvanceTarget(deviceId, epoch, ringId) ?? info.readSeq)
        : state.checkpoint.durableSeq;
    if (!_isSession(state, deviceId, epoch, token)) return;
    if (ringId != null &&
        !state.incarnationInvalid &&
        frontier > info.readSeq &&
        frontier <= info.writeSeq &&
        replayAdvance != null &&
        _batchAuthorityValid(state, frontier)) {
      final status = await replayAdvance(frontier);
      if (!_isSession(state, deviceId, epoch, token)) return;
      if (status == RingProtocol.ackOk) {
        await markAdvanced(deviceId, epoch, frontier);
      } else if (status == RingProtocol.ackRingIdMismatch) {
        noteMismatch(deviceId, epoch);
      }
    }
  }

  void endConnection(String deviceId, int epoch, {Object? sessionToken}) {
    final state = _state(deviceId, epoch);
    if (state == null) return;
    if (sessionToken != null && !identical(state.sessionToken, sessionToken)) return;
    state.connected = false;
    _devices.remove(deviceId);
  }

  void setLivePersistEnabled(String deviceId, int epoch, bool enabled) {
    final state = _state(deviceId, epoch);
    state?.liveEnabled = enabled;
  }

  LiveFrameObservation observeLiveFrame(String deviceId, int epoch, int packetCounter, int fragmentIndex) {
    final state = _state(deviceId, epoch);
    if (state == null || !state.liveEnabled) return null;
    final ordinal = state.ordinals.observe(packetCounter, fragmentIndex);
    if (ordinal == null) state.evidenceBroken = true;
    return ordinal;
  }

  void observeLiveMark(String deviceId, int epoch, LiveMarkNotification mark) {
    final state = _state(deviceId, epoch);
    if (state == null || !state.liveEnabled || state.incarnationInvalid || state.evidenceBroken) return;
    if (state.checkpoint.ringId != mark.ringId) {
      state.evidenceBroken = true;
      return;
    }
    if (mark.ringSeq > state.checkpoint.reportedWriteSeq) {
      state.checkpoint.reportedWriteSeq = mark.ringSeq;
    }
    int? boundary;
    if (state.marks.isEmpty) {
      if (mark.liveIndex == 0 && state.ordinals.lastCounter == null) {
        boundary = 0;
      } else if (state.ordinals.nextOrdinal < 0x8000) {
        boundary = state.ordinals.ordinalBoundaryFor(mark.liveIndex);
      }
    } else {
      final prev = state.marks.last;
      if (prev.ringSeq == mark.ringSeq && prev.liveIndex == mark.liveIndex) {
        return;
      }
      if (mark.ringSeq > prev.ringSeq) {
        final deltaRecords = mark.ringSeq - prev.ringSeq;
        final maxPackedFrames = deltaRecords * (RingProtocol.audioPayloadBytes ~/ 2);
        final deltaIdx = (mark.liveIndex - prev.liveIndex) & 0xFFFF;
        if (maxPackedFrames < 0x8000 && deltaIdx > 0 && deltaIdx < 0x8000 && deltaIdx <= maxPackedFrames) {
          final candidate = prev.ordinalBoundary + deltaIdx;
          if (candidate > prev.ordinalBoundary && candidate <= state.ordinals.nextOrdinal) {
            boundary = candidate;
          }
        }
      }
    }
    if (boundary == null) {
      state.evidenceBroken = true;
      return;
    }
    state.liveAnchorSeq ??= mark.ringSeq;
    state.marks.add((ringSeq: mark.ringSeq, liveIndex: mark.liveIndex, ordinalBoundary: boundary));
    final batch = state.checkpoint._batchSessions[state.batchSessionId];
    if (batchRingProofEnabled && batch != null) {
      // Bound speculative state. Discarding mappings only forces re-download.
      if (batch.marks.length >= 4096) batch.marks.removeAt(0);
      batch.marks.add(state.marks.last);
      _foldBatchSession(state, batch);
    }

    _foldProvenRanges(state);
    _queuePersistThenAdvance(state, deviceId, epoch);
  }

  void _queuePersistThenAdvance(_DeviceCustody state, String deviceId, int epoch) {
    final token = state.sessionToken;
    final ringId = state.checkpoint.ringId;
    bool stillSession() =>
        token != null && _isSession(state, deviceId, epoch, token) && state.checkpoint.ringId == ringId;
    final task = state.markTask.then((_) async {
      if (!stillSession()) return;
      await _persist(state.checkpoint);
      if (!stillSession()) return;
      final target = await validatedAdvanceTarget(deviceId, epoch, ringId);
      if (!stillSession()) return;
      final cb = state.advanceCallback;
      if (target == null || cb == null) return;
      if (!_batchAuthorityValid(state, target)) return;
      final markSeq = state.checkpoint.lastMarkSeq;
      final status = await cb(target);
      if (!stillSession()) return;
      if (status == RingProtocol.ackOk) {
        await markAdvanced(deviceId, epoch, target, markSeq: markSeq);
      } else if (status == RingProtocol.ackRingIdMismatch) {
        noteMismatch(deviceId, epoch);
      }
    });
    state.markTask = task.catchError((e) {
      Logger.debug('PendantRingCustody: mark persist/advance failed for $deviceId: $e');
    });
  }

  Future<void> recordDurableLiveFrames(
    String deviceId,
    int epoch,
    int startOrdinal,
    int endOrdinal,
    CustodyWalRef wal,
  ) async {
    final state = _state(deviceId, epoch);
    if (state == null ||
        state.evidenceBroken ||
        state.incarnationInvalid ||
        !state.liveEnabled ||
        endOrdinal <= startOrdinal) {
      return;
    }
    if (wal.fileName.isEmpty || wal.liveRingId == null || wal.liveRingId != state.checkpoint.ringId) return;
    state.durableLiveChunks.add((start: startOrdinal, end: endOrdinal, wal: wal));
    final batch = state.checkpoint._batchSessions[state.batchSessionId];
    if (batchRingProofEnabled && batch != null) {
      _addBatchChunk(batch, wal);
      _foldBatchSession(state, batch);
    }

    _foldProvenRanges(state);
    await _persist(state.checkpoint);
  }

  Future<void> recordDurableRingRange(
    String deviceId,
    int epoch,
    int ringId,
    int startSeq,
    int endSeq,
    List<CustodyWalRef> wals,
  ) async {
    if (endSeq <= startSeq || ringId == 0 || wals.isEmpty) return;
    final proof = RingRangeProof(startSeq: startSeq, endSeq: endSeq, wals: List.of(wals));
    if (!_downloadRangeMatches(proof, deviceId, ringId)) return;
    if (ringDrainRecoveryEnabled) {
      // A completed file/index transaction outlives its BLE epoch. This receipt
      // is only a claim: every ref is validated again before any ADVANCE.
      await _store.updateDownloadedRanges(deviceId, ringId, (ranges) {
        ranges.removeWhere((r) => r.startSeq == startSeq && r.endSeq == endSeq);
        ranges.add(proof);
      });
    }
    final state = ringDrainRecoveryEnabled ? _devices[deviceId] : _state(deviceId, epoch);
    if (state == null || state.incarnationInvalid || state.checkpoint.ringId != ringId || endSeq <= startSeq) {
      return;
    }
    state.checkpoint.ringRanges.add(proof);
    _foldProvenRanges(state);
    await _persist(state.checkpoint);
  }

  bool get _customValidation => _customSnapshot != null || _walValidator != walFileManagerCustodyValidator;

  bool _referenceScopeMatches(CustodyWalRef ref, String device, int? ring) {
    if (ref.liveRingId != null) {
      return ref.liveRingId == ring && (ref.liveDeviceId == device || (_customValidation && ref.liveDeviceId == null));
    }
    if (ref.downloadRingId != null) return ref.downloadRingId == ring && ref.downloadDeviceId == device;
    return _customValidation;
  }

  bool _downloadRangeMatches(RingRangeProof range, String deviceId, int ringId) =>
      range.wals.isNotEmpty &&
      range.wals.every((ref) =>
          (ref.downloadRingId == null && _customValidation) ||
          (ref.downloadRingId == ringId &&
              ref.downloadDeviceId == deviceId &&
              ref.downloadSeqStart != null &&
              ref.downloadSeqEnd != null &&
              ref.downloadSeqStart! <= range.startSeq &&
              ref.downloadSeqEnd! >= range.endSeq));

  /// Re-read the durable receipt journal even on an existing BLE epoch. An old
  /// read may have finished its disk transaction after that epoch was replaced.
  Future<void> restoreDownloadedRanges(String deviceId, int epoch, int ringId, {required int reportedReadSeq}) async {
    if (!ringDrainRecoveryEnabled) return;
    final state = _state(deviceId, epoch);
    if (state == null || state.incarnationInvalid || state.checkpoint.ringId != ringId) return;
    final token = state.sessionToken;
    final ranges = await _store.updateDownloadedRanges(deviceId, ringId, (ranges) {
      // Only INFO confirms that receipt metadata is no longer needed. Keep it
      // across a lost/delayed/ambiguous command ACK and every session teardown.
      ranges.removeWhere((r) => r.endSeq <= reportedReadSeq);
    });
    if (!_customValidation) {
      // The index is itself the crash journal for the interval between audio /
      // index commit and the separate custody checkpoint write.
      for (final wal in await WalFileManager.loadIndexedWals()) {
        final start = wal.downloadSeqStart, end = wal.downloadSeqEnd;
        if (wal.ownerUid == null ||
            wal.ownerUid!.isEmpty ||
            wal.device != deviceId ||
            wal.downloadRingId != ringId ||
            start == null ||
            end == null ||
            wal.downloadFileBytes == null ||
            wal.downloadFileBytes! <= 0 ||
            start < 0 ||
            end <= start ||
            end <= reportedReadSeq ||
            wal.storage != WalStorage.disk) {
          continue;
        }
        final name = (wal.filePath ?? wal.getFileName()).split('/').last as String;
        final ref = CustodyWalRef(
            fileName: name,
            bytes: wal.downloadFileBytes!,
            frames: wal.totalFrames,
            ownerUid: wal.ownerUid,
            fileSha256: wal.fileSha256,
            downloadRingId: ringId,
            downloadSeqStart: start,
            downloadSeqEnd: end,
            downloadDeviceId: deviceId);
        final proof = RingRangeProof(startSeq: start, endSeq: end, wals: [ref]);
        if (!ranges.any((r) => jsonEncode(r.toJson()) == jsonEncode(proof.toJson()))) ranges.add(proof);
      }
    }
    if (token == null || !_isSession(state, deviceId, epoch, token) || state.checkpoint.ringId != ringId) return;
    for (final range in ranges) {
      if (range.endSeq <= state.checkpoint.reportedReadSeq) continue;
      if (!state.checkpoint.ringRanges.any((r) => jsonEncode(r.toJson()) == jsonEncode(range.toJson()))) {
        state.checkpoint.ringRanges.add(range);
      }
    }
    await _validateCheckpoint(state.checkpoint);
    if (!_isSession(state, deviceId, epoch, token) || state.checkpoint.ringId != ringId) return;
    await _persist(state.checkpoint);
  }

  Future<bool> isDurableLiveRecord(String deviceId, int? ringId, int seq, {CustodyProofMemo? memo}) async {
    if (ringId == null) return false;
    final state = _devices[deviceId];
    if (state == null) return false;
    final ranges = await validatedRecordRanges(deviceId, state.epoch, ringId,
        startSeq: seq,
        endSeq: seq + 1,
        readValidator: memo == null ? null : (memo._validator ??= await createReadValidator()));
    return ranges.any((r) => r.$1 <= seq && seq < r.$2);
  }

  /// Stable exact ranges for avoiding duplicate files inside an interrupted
  /// READ. Skipping payload is not ADVANCE authority: the release path validates
  /// the refs again, so later deletion/index loss still retains the pendant copy.
  Future<List<(int, int)>> validatedRecordRanges(String deviceId, int epoch, int ringId,
      {int? startSeq, int? endSeq, CustodyReadValidation? readValidator}) async {
    final state = _state(deviceId, epoch);
    if (state == null || state.incarnationInvalid || state.checkpoint.ringId != ringId) return [];
    final token = state.sessionToken;
    final cp = state.checkpoint;
    final candidates = <(int, int, List<CustodyWalRef>)>[
      for (final r in cp.ringRanges)
        if ((startSeq == null || r.endSeq > startSeq) && (endSeq == null || r.startSeq < endSeq))
          (r.startSeq, r.endSeq, List.of(r.wals)),
      for (final r in [...cp.liveRanges, ...state.releasedLiveRanges])
        if ((startSeq == null || r.endSeq > startSeq) && (endSeq == null || r.startSeq < endSeq))
          (r.startSeq, r.endSeq, List.of(r.wals)),
    ];
    final result = <(int, int)>[];
    final CustodyWalValidator validate = readValidator == null ? await _validationSnapshot() : readValidator.call;
    final checked = <String, Future<bool>>{};
    for (final range in candidates) {
      var valid = range.$3.isNotEmpty && range.$3.every((r) => _referenceScopeMatches(r, deviceId, ringId));
      for (final ref in range.$3) {
        if (!await checked.putIfAbsent(jsonEncode(ref.toJson()), () => validate(ref))) {
          valid = false;
          break;
        }
      }
      if (token == null ||
          !_isSession(state, deviceId, epoch, token) ||
          !identical(state.checkpoint, cp) ||
          cp.ringId != ringId) {
        return [];
      }
      if (valid && !result.contains((range.$1, range.$2))) result.add((range.$1, range.$2));
    }
    return readValidator != null && !readValidator.isCurrent ? [] : result;
  }

  int? advanceTarget(String deviceId, int epoch) {
    final state = _state(deviceId, epoch);
    if (state == null || state.incarnationInvalid) return null;
    var target = state.durableFrontier;
    final cap = state.checkpoint.reportedWriteSeq;
    if (cap > 0 && target > cap) target = cap;
    if (target <= state.checkpoint.lastAdvancedSeq) return null;
    return target;
  }

  bool _batchAuthorityValid(_DeviceCustody state, int target) {
    for (final range in state.checkpoint.ringRanges) {
      if (range.endSeq <= state.checkpoint.reportedReadSeq || range.startSeq >= target) continue;
      for (final ref in range.wals) {
        if (ref.ownerUid != null && SharedPreferencesUtil().uid != ref.ownerUid) {
          return false;
        }
      }
    }
    for (final range in state.checkpoint.liveRanges) {
      if (range.endSeq <= state.checkpoint.reportedReadSeq || range.startSeq >= target) continue;
      for (final ref in range.wals) {
        if (ref.batchLiveSession != null &&
            (!batchRingProofEnabled ||
                ref.ownerUid == null ||
                ref.ownerUid != SharedPreferencesUtil().uid ||
                ref.liveRingId != state.checkpoint.ringId ||
                ref.liveDeviceId != state.checkpoint.deviceId)) {
          return false;
        }
      }
    }
    return true;
  }

  Future<int?> validatedAdvanceTarget(String deviceId, int epoch, int? ringId,
      {CustodyReadValidation? readValidator}) async {
    final state = _state(deviceId, epoch);
    if (state?.incarnationInvalid ?? true) return null;
    final token = state!.sessionToken;
    final cpRingId = state.checkpoint.ringId;
    if (ringId != null && cpRingId != ringId) return null;
    var target = advanceTarget(deviceId, epoch);
    if (target == null) return null;
    final from = state.checkpoint.reportedReadSeq;
    if (state.checkpoint.ringRanges.any((r) => r.wals.isEmpty) ||
        state.checkpoint.liveRanges.any((r) => r.wals.isEmpty)) {
      await _validateCheckpoint(state.checkpoint);
      return null;
    }
    final refs = <CustodyWalRef>[];
    for (final r in state.checkpoint.ringRanges) {
      if (r.endSeq > from && r.startSeq < target) refs.addAll(r.wals);
    }
    for (final r in state.checkpoint.liveRanges) {
      if (r.endSeq > from && r.startSeq < target) refs.addAll(r.wals);
    }
    final CustodyWalValidator validate = readValidator == null ? await _validationSnapshot() : readValidator.call;
    final checked = <String>{};
    for (final w in refs) {
      if (!checked.add(jsonEncode(w.toJson()))) continue;
      final ok = _referenceScopeMatches(w, deviceId, ringId) && await validate(w);
      final s = _state(deviceId, epoch);
      if (s == null || !identical(s.sessionToken, token) || s.checkpoint.ringId != cpRingId) return null;
      if (readValidator != null && !readValidator.isCurrent) return null;
      if (!ok) {
        s.checkpoint.ringRanges.removeWhere((r) => r.wals.contains(w));
        s.checkpoint.liveRanges.removeWhere((r) => r.wals.contains(w));
        var frontier = s.checkpoint.reportedReadSeq;
        var moved = true;
        while (moved) {
          moved = false;
          for (final r in s.checkpoint.ringRanges) {
            if (r.startSeq <= frontier && r.endSeq > frontier) {
              frontier = r.endSeq;
              moved = true;
            }
          }
          for (final r in s.checkpoint.liveRanges) {
            if (r.startSeq <= frontier && r.endSeq > frontier) {
              frontier = r.endSeq;
              moved = true;
            }
          }
        }
        s.checkpoint.durableSeq = frontier;
        await _persist(s.checkpoint);
        return null;
      }
    }
    final s = _state(deviceId, epoch);
    if (s == null || !identical(s.sessionToken, token) || s.checkpoint.ringId != cpRingId) return null;
    await _persist(s.checkpoint);
    final after = _state(deviceId, epoch);
    if (after == null || !identical(after.sessionToken, token) || after.checkpoint.ringId != cpRingId) return null;
    final current = advanceTarget(deviceId, epoch);
    if (current == null ||
        (readValidator != null && !readValidator.isCurrent) ||
        !_batchAuthorityValid(after, current)) {
      return null;
    }
    return current < target ? current : target;
  }

  Future<void> markAdvanced(String deviceId, int epoch, int seq, {int? markSeq}) async {
    final state = _state(deviceId, epoch);
    if (state == null) return;
    if (seq > state.checkpoint.lastAdvancedSeq) state.checkpoint.lastAdvancedSeq = seq;
    if (ringDrainRecoveryEnabled) {
      // An OK ACK proves the device is at least here. Do not re-open every old
      // WAL/index for each subsequent chunk (quadratic I/O on a long read).
      _noteDeviceReadFloor(state, seq);
      _foldProvenRanges(state);
    }
    if (!ringDrainRecoveryEnabled) _noteDeviceReadFloor(state, seq);
    if (markSeq != null) state.checkpoint.lastAdvancedMarkSeq = markSeq;
    await _persist(state.checkpoint);
  }

  /// The pendant acknowledged an advance to [seq], so its read pointer is at
  /// least there and the proofs for everything below are spent. Dropping them
  /// here keeps each later check proportional to what is still unreleased;
  /// they used to pile up until the next INFO and every check walked them all.
  void _noteDeviceReadFloor(_DeviceCustody state, int seq) {
    final cp = state.checkpoint;
    if (seq > cp.reportedReadSeq) cp.reportedReadSeq = seq;
    if (seq > cp.durableSeq) cp.durableSeq = seq;
    final released = cp.liveRanges.where((r) => r.endSeq <= cp.reportedReadSeq).toList();
    if (released.isNotEmpty) {
      cp.liveRanges.removeWhere((r) => r.endSeq <= cp.reportedReadSeq);
      state.releasedLiveRanges.addAll(released);
      final excess = state.releasedLiveRanges.length - _DeviceCustody.maxReleasedLiveRanges;
      if (excess > 0) state.releasedLiveRanges.removeRange(0, excess);
    }
    cp.ringRanges.removeWhere((r) => r.endSeq <= cp.reportedReadSeq);
  }

  bool hasConnection(String deviceId, int epoch) => _state(deviceId, epoch)?.connected ?? false;

  int? acknowledgedReadSeqFor(String deviceId, int epoch, int ringId) {
    final state = _state(deviceId, epoch);
    return state != null && !state.incarnationInvalid && state.checkpoint.ringId == ringId
        ? state.checkpoint.reportedReadSeq
        : null;
  }

  bool isIncarnationInvalid(String deviceId, int epoch) => _state(deviceId, epoch)?.incarnationInvalid ?? false;

  int? latestEpoch(String deviceId) {
    final s = _devices[deviceId];
    return (s != null && s.connected) ? s.epoch : null;
  }

  BatchLiveContext? batchLiveContext(String deviceId) {
    if (!batchRingProofEnabled) return null;
    final s = _devices[deviceId];
    final ring = s?.checkpoint.ringId;
    if (s == null || !s.connected || !s.liveEnabled || s.incarnationInvalid || ring == null) return null;
    return BatchLiveContext(deviceId, ring, s.epoch, s.batchSessionId);
  }

  /// Called only after the batch writer accepted a whole frame. A declined
  /// append must leave this tracker untouched for the ordinary WAL fallback.
  int? observeBatchFrame(BatchLiveContext context, int counter, int fragment) {
    if (batchLiveContext(context.deviceId) != context) return null;
    final s = _devices[context.deviceId]!;
    final ordinal = observeLiveFrame(context.deviceId, context.epoch, counter, fragment);
    if (ordinal == null) return null;
    final sessions = s.checkpoint._batchSessions;
    if (!sessions.containsKey(context.sessionId)) {
      if (sessions.length >= 64) sessions.remove(sessions.keys.first);
      sessions[context.sessionId] = _BatchLiveSession(context.sessionId)
        ..marks.addAll(s.marks)
        ..chunks.addAll(s.durableLiveChunks);
    }
    return ordinal;
  }

  static void _addBatchChunk(_BatchLiveSession session, CustodyWalRef ref) {
    if (ref.liveOrdinalStart == null || ref.liveOrdinalEnd == null) return;
    session.chunks.removeWhere((c) => c.wal.fileName == ref.fileName);
    if (session.chunks.length >= 4096) session.chunks.removeAt(0);
    session.chunks.add((start: ref.liveOrdinalStart!, end: ref.liveOrdinalEnd!, wal: ref));
  }

  void _foldBatchSession(_DeviceCustody state, _BatchLiveSession session) {
    // Use the ordinary exact interval union and mark-pair implementation.
    // Historical sessions have their own coordinates, never the new tracker.
    final folding = _DeviceCustody(state.checkpoint)
      ..marks.addAll(session.marks)
      ..durableLiveChunks.addAll(session.chunks);
    _foldProvenRanges(folding);
    session.marks
      ..clear()
      ..addAll(folding.marks);
    session.chunks
      ..clear()
      ..addAll(folding.durableLiveChunks);
  }

  Future<void> recordDurableBatchWal(Wal wal) async {
    if (!batchRingProofEnabled) return;
    final device = wal.liveDeviceId;
    final s = device == null ? null : _devices[device];
    final token = s?.sessionToken;
    if (s == null || token == null || !s.connected) return;
    await _recordBatchWal(s, device!, s.epoch, token, wal);
  }

  Future<void> _recordBatchWal(_DeviceCustody s, String device, int epoch, Object token, Wal wal) async {
    final checkpoint = s.checkpoint;
    final session = checkpoint._batchSessions[wal.batchLiveSession];
    final start = wal.liveOrdinalStart, end = wal.liveOrdinalEnd;
    if (session == null ||
        s.incarnationInvalid ||
        wal.liveRingId != s.checkpoint.ringId ||
        wal.liveDeviceId != device ||
        wal.ownerUid == null ||
        wal.ownerUid!.isEmpty ||
        wal.ownerUid != SharedPreferencesUtil().uid ||
        start == null ||
        end == null ||
        start < 0 ||
        end <= start ||
        end - start > wal.totalFrames ||
        wal.storage != WalStorage.disk) {
      return;
    }
    final ref = CustodyWalRef(
        fileName: wal.filePath ?? wal.getFileName(),
        bytes: wal.storageTotalBytes,
        frames: wal.totalFrames,
        liveRingId: wal.liveRingId,
        liveOrdinalStart: start,
        liveOrdinalEnd: end,
        batchLiveSession: wal.batchLiveSession,
        liveDeviceId: wal.liveDeviceId,
        ownerUid: wal.ownerUid,
        fileSha256: wal.fileSha256);
    if (!await _walValidator(ref) || !_isSession(s, device, epoch, token)) return;
    if (!identical(s.checkpoint, checkpoint) ||
        checkpoint.ringId != wal.liveRingId ||
        !identical(checkpoint._batchSessions[wal.batchLiveSession], session) ||
        wal.ownerUid != SharedPreferencesUtil().uid) {
      return;
    }
    _addBatchChunk(session, ref);
    // A broken current run cannot prove later packets. Already validated old
    // session mappings can still recover their own exact intervals.
    if (session.id == s.batchSessionId && s.evidenceBroken) return;
    if (session.id == s.batchSessionId) {
      s.durableLiveChunks.removeWhere((c) => c.wal.fileName == ref.fileName);
      s.durableLiveChunks.add((start: start, end: end, wal: ref));
    }
    _foldBatchSession(s, session);
    _foldProvenRanges(s);
    await _persist(s.checkpoint);
  }

  Future<void> _restoreBatchProofs(_DeviceCustody s, String device, int epoch, Object token) async {
    for (final session in s.checkpoint._batchSessions.values.toList()) {
      for (final chunk in session.chunks.toList()) {
        final valid = await _walValidator(chunk.wal);
        if (!_isSession(s, device, epoch, token)) return;
        if (!valid) session.chunks.remove(chunk);
      }
    }
    final indexed = await WalFileManager.loadIndexedWals();
    if (!_isSession(s, device, epoch, token)) return;
    for (final wal in indexed) {
      if (wal.batchLiveSession != null && wal.liveDeviceId == device) {
        await _recordBatchWal(s, device, epoch, token, wal);
        if (!_isSession(s, device, epoch, token)) return;
      }
    }
  }

  int? currentRingId(String deviceId) {
    final s = _devices[deviceId];
    return (s != null && s.connected) ? s.checkpoint.ringId : null;
  }

  LiveFrameObservation observeLiveFrameLatest(String deviceId, int packetCounter, int fragmentIndex) {
    final epoch = latestEpoch(deviceId);
    if (epoch == null) return null;
    return observeLiveFrame(deviceId, epoch, packetCounter, fragmentIndex);
  }

  _DeviceCustody? _liveProving(String deviceId, int epoch) {
    final state = _state(deviceId, epoch);
    if (state == null || !state.liveEnabled || state.evidenceBroken || state.incarnationInvalid) return null;
    if (state.marks.isEmpty || state.liveAnchorSeq == null) return null;
    return state;
  }

  /// The ring sequence from which this connection's live marks can prove
  /// records, or null when it has no marks it can trust.
  ///
  /// With live persist on, the ring always holds audio the phone has received
  /// live and not yet released. From this sequence on, the live proof releases
  /// it as the phone stores it, and a ring read would only fetch a second copy.
  /// Below it nothing can be proven live (a range needs a mark on each side),
  /// so that stretch is what a ring read is for.
  int? liveProofStartSeq(String deviceId, int epoch) => _liveProving(deviceId, epoch)?.liveAnchorSeq;

  /// Whether a live mark covers the ring as far as [writeSeq], a committed
  /// write position the pendant reported.
  ///
  /// The pendant emits a mark at the committed write position with every commit
  /// of an unbroken live run, and none once a record the phone was not sent has
  /// joined the ring. So this holds exactly when nothing unsent is waiting. It
  /// allows no slack: a few unmarked records followed by silence would
  /// otherwise never be read. The mark for a commit is notified just after the
  /// INFO that reported it, so callers give it a moment to arrive; judging too
  /// early only costs a short read of audio that also arrived live.
  bool liveMarksReach(String deviceId, int epoch, int writeSeq) {
    final state = _liveProving(deviceId, epoch);
    return state != null && state.marks.last.ringSeq >= writeSeq;
  }

  /// Whether everything still unread on the ring is audio this connection's
  /// live proof will release, so there is nothing a ring read should fetch.
  bool liveRunCoversUnread(String deviceId, int epoch, RingInfo info) {
    final state = _liveProving(deviceId, epoch);
    if (state == null) return false;
    if (info.ringId == null || info.ringId != state.checkpoint.ringId) return false;
    return info.readSeq >= state.liveAnchorSeq! && liveMarksReach(deviceId, epoch, info.writeSeq);
  }

  int? durableFrontierFor(String deviceId, int epoch) {
    final state = _state(deviceId, epoch);
    return state?.durableFrontier;
  }

  void noteMismatch(String deviceId, int epoch) {
    final state = _state(deviceId, epoch);
    if (state == null) return;
    state.liveEnabled = false;
    state.evidenceBroken = true;
    state.incarnationInvalid = true;
    state.durableLiveChunks.clear();
    state.marks.clear();
    state.liveAnchorSeq = null;
    state.releasedLiveRanges.clear();
    final cp = state.checkpoint;
    cp._batchSessions.clear();
    cp.liveRanges.clear();
    cp.ringRanges.clear();
    cp.durableSeq = 0;
    cp.lastAdvancedSeq = 0;
    cp.lastMarkSeq = null;
    cp.lastMarkLiveIndex = null;
    cp.lastAdvancedMarkSeq = null;
    unawaited(
      _persist(cp).catchError((e) {
        Logger.debug('PendantRingCustody: mismatch-invalidation persist failed for $deviceId: $e');
      }),
    );
  }

  void noteInfo(String deviceId, int epoch, RingInfo info) {
    final state = _state(deviceId, epoch);
    if (state == null) return;
    final cp = state.checkpoint;
    if (info.ringId != null && info.ringId != cp.ringId) {
      state.checkpoint = RingCustodyCheckpoint(deviceId: deviceId, ringId: info.ringId);
      state.marks.clear();
      state.liveAnchorSeq = null;
      state.releasedLiveRanges.clear();
      state.durableLiveChunks.clear();
      state.evidenceBroken = false;
      state.incarnationInvalid = false;
      state.ordinals = LivePacketOrdinals();
      state.batchSessionId = const Uuid().v4();
      final ncp = state.checkpoint;
      ncp.reportedReadSeq = info.readSeq;
      ncp.reportedWriteSeq = info.writeSeq;
      ncp.durableSeq = info.readSeq;
      unawaited(
        _persist(ncp).catchError((e) {
          Logger.debug('PendantRingCustody: reincarnation persist failed for $deviceId: $e');
        }),
      );
      return;
    }
    if (cp.ringId != null && info.ringId == null) return;
    if (ringDrainRecoveryEnabled && info.readSeq < cp.reportedReadSeq) {
      // A fresh device report wins over a command ACK. Rebuild from receipts
      // rather than trusting the old in-memory high-water mark.
      cp.durableSeq = info.readSeq;
      cp.lastAdvancedSeq = info.readSeq;
    }
    cp.reportedReadSeq = info.readSeq;
    if (info.readSeq > cp.durableSeq) cp.durableSeq = info.readSeq;
    cp.reportedWriteSeq = info.writeSeq;
  }

  void _foldProvenRanges(_DeviceCustody state) {
    if (!state.evidenceBroken && state.marks.length >= 2) {
      var lastFolded = -1;
      for (var i = 1; i < state.marks.length; i++) {
        final prev = state.marks[i - 1];
        final cur = state.marks[i];
        if (cur.ringSeq <= prev.ringSeq || cur.ordinalBoundary <= prev.ordinalBoundary) {
          state.evidenceBroken = true;
          break;
        }
        final already = cur.ringSeq <= state.checkpoint.reportedReadSeq ||
            state.checkpoint.liveRanges.any((r) => r.startSeq == prev.ringSeq && r.endSeq == cur.ringSeq);
        if (already) {
          lastFolded = i - 1;
          continue;
        }
        if (!_ordinalsDurable(state, prev.ordinalBoundary, cur.ordinalBoundary)) break;
        state.checkpoint.liveRanges.add(
          LiveRangeProof(
            startSeq: prev.ringSeq,
            endSeq: cur.ringSeq,
            startLiveOrdinal: prev.ordinalBoundary,
            endLiveOrdinal: cur.ordinalBoundary,
            wals: _walsCovering(state, prev.ordinalBoundary, cur.ordinalBoundary),
          ),
        );
        state.checkpoint.lastMarkSeq = cur.ringSeq;
        state.checkpoint.lastMarkLiveIndex = cur.liveIndex;
        lastFolded = i - 1;
      }
      if (lastFolded >= 0) {
        state.marks.removeRange(0, lastFolded);
        if (state.marks.isNotEmpty) {
          final floor = state.marks.first.ordinalBoundary;
          state.durableLiveChunks.removeWhere((c) => c.end <= floor);
        }
      }
    }
    var frontier = state.checkpoint.reportedReadSeq;
    if (state.checkpoint.durableSeq > frontier) frontier = state.checkpoint.durableSeq;
    var moved = true;
    while (moved) {
      moved = false;
      for (final r in state.checkpoint.ringRanges) {
        if (r.startSeq <= frontier && r.endSeq > frontier) {
          frontier = r.endSeq;
          moved = true;
        }
      }
      for (final r in state.checkpoint.liveRanges) {
        if (r.startSeq <= frontier && r.endSeq > frontier) {
          frontier = r.endSeq;
          moved = true;
        }
      }
    }
    if (frontier > state.checkpoint.durableSeq) state.checkpoint.durableSeq = frontier;
    state.checkpoint.liveRanges.removeWhere((r) => r.endSeq <= state.checkpoint.reportedReadSeq);
    state.checkpoint.ringRanges.removeWhere((r) => r.endSeq <= state.checkpoint.reportedReadSeq);
  }

  bool _ordinalsDurable(_DeviceCustody state, int start, int end) {
    var cursor = start;
    var moved = true;
    while (moved && cursor < end) {
      moved = false;
      for (final c in state.durableLiveChunks) {
        if (c.start <= cursor && c.end > cursor) {
          cursor = c.end;
          moved = true;
        }
      }
    }
    return cursor >= end;
  }

  List<CustodyWalRef> _walsCovering(_DeviceCustody state, int start, int end) {
    final refs = <CustodyWalRef>[];
    for (final c in state.durableLiveChunks) {
      if (c.end > start && c.start < end && !refs.any((r) => r.fileName == c.wal.fileName)) {
        refs.add(c.wal);
      }
    }
    return refs;
  }

  Future<bool> _validateCheckpoint(RingCustodyCheckpoint cp) async {
    if (cp.liveRanges.isEmpty && cp.ringRanges.isEmpty) {
      cp.durableSeq = cp.reportedReadSeq;
      if (cp.lastAdvancedSeq > cp.durableSeq) cp.lastAdvancedSeq = cp.durableSeq;
      return true;
    }
    final validate = await _validationSnapshot();
    cp.liveRanges.removeWhere((r) => r.wals.any((ref) => !_referenceScopeMatches(ref, cp.deviceId, cp.ringId)));
    cp.ringRanges.removeWhere((r) => r.wals.isEmpty);
    cp.liveRanges.removeWhere((r) => r.wals.isEmpty);
    if (ringDrainRecoveryEnabled) {
      // A deleted/foreign/unindexed WAL invalidates its own range, not every
      // unrelated downloaded range. Never carry durableSeq across that hole.
      cp.liveRanges.removeWhere((r) => r.endSeq <= cp.reportedReadSeq);
      cp.ringRanges.removeWhere((r) => r.endSeq <= cp.reportedReadSeq);
      for (final range in List.of(cp.liveRanges)) {
        for (final ref in range.wals) {
          if (!await validate(ref)) {
            cp.liveRanges.remove(range);
            break;
          }
        }
      }
      for (final range in List.of(cp.ringRanges)) {
        if (cp.ringId == null || !_downloadRangeMatches(range, cp.deviceId, cp.ringId!)) {
          cp.ringRanges.remove(range);
          continue;
        }
        for (final ref in range.wals) {
          if (!await validate(ref)) {
            cp.ringRanges.remove(range);
            break;
          }
        }
      }
      cp.durableSeq = cp.reportedReadSeq;
    }
    var provable = cp.reportedReadSeq;
    var moved = true;
    while (moved) {
      moved = false;
      for (final r in cp.ringRanges) {
        if (r.startSeq <= provable && r.endSeq > provable) {
          provable = r.endSeq;
          moved = true;
        }
      }
      for (final r in cp.liveRanges) {
        if (r.startSeq <= provable && r.endSeq > provable) {
          provable = r.endSeq;
          moved = true;
        }
      }
    }
    if (cp.durableSeq > provable) cp.durableSeq = provable;
    if (cp.lastAdvancedSeq > provable) cp.lastAdvancedSeq = provable;
    if (ringDrainRecoveryEnabled) {
      cp.durableSeq = provable;
      return true;
    }
    for (final r in [...cp.liveRanges, ...cp.ringRanges]) {
      for (final w in (r is LiveRangeProof ? r.wals : (r as RingRangeProof).wals)) {
        if (!await validate(w)) return false;
      }
    }
    return true;
  }

  /// Completes once every checkpoint write queued so far has settled (written or
  /// failed), including writes queued while waiting and the persists that open
  /// sessions' live-mark chains still owe. Mismatch invalidation, ring
  /// reincarnation and live marks persist without awaiting, so this is the
  /// completion a caller waits on before tearing the custody directory down
  /// (#20500). It also waits for any advance callback a mark chain is running.
  Future<void> flush() async {
    while (true) {
      final saves = _saveQueue;
      final marks = _markTasks();
      await saves;
      await Future.wait(marks);
      // A checkpoint queued during these waits reaches the I/O queue only after
      // its predecessor's save, so both queues are re-checked after the store.
      await _store.flush();
      // A mark step chained during these waits may not have queued its persist yet,
      // so an unchanged save queue alone does not prove every chain has drained.
      if (identical(saves, _saveQueue) && _sameFutures(marks, _markTasks())) return;
    }
  }

  List<Future<void>> _markTasks() => [for (final state in _devices.values) state.markTask];

  static bool _sameFutures(List<Future<void>> a, List<Future<void>> b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (!identical(a[i], b[i])) return false;
    }
    return true;
  }

  Future<void> _persist(RingCustodyCheckpoint cp) {
    if (cp.ringId == null) return Future.value();
    final payload = cp.toJson();
    final task = _saveQueue.then((_) => _store.saveJson(cp.deviceId, payload));
    _saveQueue = task.catchError((_) {});
    return task;
  }
}

class PendantCustodyStore {
  static const _dirName = 'pendant_ring_custody';
  static const _fileVersion = 1;

  final Future<Directory> Function()? _directoryProvider;

  Future<void> _ioQueue = Future.value();

  PendantCustodyStore({Future<Directory> Function()? directoryProvider}) : _directoryProvider = directoryProvider;

  Future<Directory> _directory() async {
    final provider = _directoryProvider;
    if (provider != null) return provider();
    final dir = await getApplicationDocumentsDirectory();
    return Directory('${dir.path}/$_dirName');
  }

  String _filePath(Directory dir, String deviceId) =>
      '${dir.path}/custody_${deviceId.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_')}.json';

  /// Completes once the I/O queue is idle (every queued read or write settled,
  /// written or failed), including work queued while waiting.
  Future<void> flush() async {
    Future<void> queued;
    do {
      queued = _ioQueue;
      await queued;
    } while (!identical(queued, _ioQueue));
  }

  Future<RingCustodyCheckpoint?> load(String deviceId) {
    RingCustodyCheckpoint? result;
    final task = _ioQueue.then((_) async {
      try {
        final dir = await _directory();
        final file = File(_filePath(dir, deviceId));
        if (!await file.exists()) return;
        final decoded = jsonDecode(await file.readAsString());
        if (decoded is! Map<String, dynamic> || decoded['version'] != _fileVersion) return;
        final cp = RingCustodyCheckpoint.fromJson(decoded);
        if (cp == null || cp.deviceId != deviceId) return;
        result = cp;
      } catch (e) {
        Logger.debug('PendantCustodyStore: load failed for $deviceId: $e');
      }
    });
    _ioQueue = task.catchError((_) {});
    return task.then((_) => result);
  }

  Future<void> saveJson(String deviceId, Map<String, dynamic> payload) {
    final task = _ioQueue.then((_) async {
      final dir = await _directory();
      await dir.create(recursive: true);
      final target = File(_filePath(dir, deviceId));
      final tmp = File('${target.path}.tmp');
      await tmp.writeAsString(jsonEncode({'version': _fileVersion, ...payload}), flush: true);
      await tmp.rename(target.path);
    });
    _ioQueue = task.catchError((_) {});
    return task;
  }

  /// Atomic, serialized read/modify/write, separate from session snapshots.
  /// A stale session checkpoint can never overwrite a completed download receipt.
  Future<List<RingRangeProof>> updateDownloadedRanges(
    String deviceId,
    int ringId, [
    void Function(List<RingRangeProof>)? update,
  ]) {
    final result = <RingRangeProof>[];
    final task = _ioQueue.then((_) async {
      final dir = await _directory();
      final target = File('${_filePath(dir, deviceId)}.downloads.$ringId');
      if (await target.exists()) {
        try {
          final json = jsonDecode(await target.readAsString());
          if (json is Map && json['device'] == deviceId && json['ring'] == ringId && json['ranges'] is List) {
            for (final raw in json['ranges']) {
              final range = RingRangeProof.fromJson(raw);
              if (range != null) result.add(range);
            }
          }
        } catch (error) {
          Logger.debug('PendantCustodyStore: unreadable download receipts: $error');
        }
      }
      if (update == null) return;
      update(result);
      await dir.create(recursive: true);
      final tmp = File('${target.path}.tmp');
      await tmp.writeAsString(
          jsonEncode({
            'device': deviceId,
            'ring': ringId,
            'ranges': [for (final range in result) range.toJson()],
          }),
          flush: true);
      await tmp.rename(target.path);
    });
    _ioQueue = task.catchError((_) {});
    return task.then((_) => result);
  }

  Future<void> delete(String deviceId) {
    final task = _ioQueue.then((_) async {
      try {
        final dir = await _directory();
        final file = File(_filePath(dir, deviceId));
        if (await file.exists()) await file.delete();
      } catch (e) {
        Logger.debug('PendantCustodyStore: delete failed for $deviceId: $e');
      }
    });
    _ioQueue = task.catchError((_) {});
    return task;
  }
}
