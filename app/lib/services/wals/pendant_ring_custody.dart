import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

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

  const CustodyWalRef({
    required this.fileName,
    required this.bytes,
    required this.frames,
    this.liveRingId,
    this.liveOrdinalStart,
    this.liveOrdinalEnd,
  });

  Map<String, dynamic> toJson() => {
        'file': fileName,
        'bytes': bytes,
        'frames': frames,
        if (liveRingId != null) 'live_ring': liveRingId,
        if (liveOrdinalStart != null) 'live_start': liveOrdinalStart,
        if (liveOrdinalEnd != null) 'live_end': liveOrdinalEnd,
      };

  static CustodyWalRef? fromJson(Object? json) {
    if (json is! Map) return null;
    final file = json['file'], bytes = json['bytes'], frames = json['frames'];
    if (file is! String || bytes is! int || frames is! int) return null;
    int? asInt(Object? v) => v is int ? v : null;
    return CustodyWalRef(
      fileName: file,
      bytes: bytes,
      frames: frames,
      liveRingId: asInt(json['live_ring']),
      liveOrdinalStart: asInt(json['live_start']),
      liveOrdinalEnd: asInt(json['live_end']),
    );
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
    return RingCustodyCheckpoint(
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
  }
}

typedef CustodyWalValidator = Future<bool> Function(CustodyWalRef ref);

Future<bool> walFileManagerCustodyValidator(CustodyWalRef ref) async {
  try {
    final wals = await WalFileManager.loadWals();
    Wal? indexed;
    for (final wal in wals) {
      final name =
          (wal.filePath != null && wal.filePath!.isNotEmpty) ? wal.filePath!.split('/').last : wal.getFileName();
      if (name == ref.fileName) {
        indexed = wal;
        break;
      }
    }
    if (indexed == null) return false;
    if (indexed.totalFrames != ref.frames) return false;
    if (ref.liveRingId != null && indexed.liveRingId != ref.liveRingId) return false;
    if (ref.liveOrdinalStart != null && indexed.liveOrdinalStart != ref.liveOrdinalStart) return false;
    if (ref.liveOrdinalEnd != null && indexed.liveOrdinalEnd != ref.liveOrdinalEnd) return false;
    final path = await Wal.getFilePath(ref.fileName);
    if (path == null) return false;
    final file = File(path);
    if (!file.existsSync()) return false;
    return (await file.length()) == ref.bytes;
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
  Object? sessionToken;
  RingCustodyCheckpoint checkpoint;
  bool liveEnabled = false;
  bool connected = false;

  bool incarnationInvalid = false;

  LivePacketOrdinals ordinals = LivePacketOrdinals();

  final List<({int ringSeq, int liveIndex, int ordinalBoundary})> marks = [];

  final List<({int start, int end, CustodyWalRef wal})> durableLiveChunks = [];

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

class PendantRingCustody {
  final Map<String, _DeviceCustody> _devices = {};
  final PendantCustodyStore _store;
  final CustodyWalValidator _walValidator;

  Future<void> _saveQueue = Future.value();

  PendantRingCustody({PendantCustodyStore? store, CustodyWalValidator? walValidator})
      : _store = store ?? PendantCustodyStore(),
        _walValidator = walValidator ?? walFileManagerCustodyValidator;

  static final PendantRingCustody shared = PendantRingCustody();

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
      state.durableLiveChunks.clear();
      state.evidenceBroken = false;
      state.ordinals = LivePacketOrdinals();
    } else {
      state = _DeviceCustody(RingCustodyCheckpoint(deviceId: deviceId))
        ..epoch = epoch
        ..sessionToken = token;
      _devices[deviceId] = state;
    }
    state.connected = true;
    state.advanceCallback = onAdvanceReady ?? replayAdvance;
    state.marks.clear();
    state.durableLiveChunks.clear();
    state.evidenceBroken = false;
    state.incarnationInvalid = false;
    state.ordinals = LivePacketOrdinals();

    final caps = effectiveCaps ?? info.effectiveCaps;
    final ringId = (caps & RingProtocol.capRingId) != 0 ? info.ringId : null;

    if (ringId != null) {
      final persisted = await _store.load(deviceId);
      if (!_isSession(state, deviceId, epoch, token)) return;
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
    if (info.readSeq > state.checkpoint.durableSeq) state.checkpoint.durableSeq = info.readSeq;

    final frontier = state.checkpoint.durableSeq;
    if (ringId != null &&
        !state.incarnationInvalid &&
        frontier > info.readSeq &&
        frontier <= info.writeSeq &&
        replayAdvance != null) {
      final status = await replayAdvance(frontier);
      if (!_isSession(state, deviceId, epoch, token)) return;
      if (status == RingProtocol.ackOk) {
        state.checkpoint.lastAdvancedSeq = frontier;
        await _persist(state.checkpoint);
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
    state.marks.add((ringSeq: mark.ringSeq, liveIndex: mark.liveIndex, ordinalBoundary: boundary));

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
    final state = _state(deviceId, epoch);
    if (state == null || state.incarnationInvalid || state.checkpoint.ringId != ringId || endSeq <= startSeq) {
      return;
    }
    state.checkpoint.ringRanges.add(RingRangeProof(startSeq: startSeq, endSeq: endSeq, wals: wals));
    _foldProvenRanges(state);
    await _persist(state.checkpoint);
  }

  Future<bool> isDurableLiveRecord(String deviceId, int? ringId, int seq) async {
    if (ringId == null) return false;
    final state = _devices[deviceId];
    final token = state?.sessionToken;
    final cp = state?.checkpoint;
    if (cp == null || cp.ringId != ringId) return false;
    final ranges = List.of(cp.liveRanges);
    for (final r in ranges) {
      if (seq >= r.startSeq && seq < r.endSeq) {
        for (final w in r.wals) {
          if (!await _walValidator(w)) return false;
        }
        final s = _devices[deviceId];
        if (s == null ||
            !identical(s.checkpoint, cp) ||
            !identical(s.sessionToken, token) ||
            s.checkpoint.ringId != ringId) {
          return false;
        }
        return true;
      }
    }
    return false;
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

  Future<int?> validatedAdvanceTarget(String deviceId, int epoch, int? ringId) async {
    final state = _state(deviceId, epoch);
    if (state?.incarnationInvalid ?? true) return null;
    final token = state!.sessionToken;
    final cpRingId = state.checkpoint.ringId;
    if (ringId != null && cpRingId != ringId) return null;
    var target = advanceTarget(deviceId, epoch);
    if (target == null) return null;
    final from = state.checkpoint.reportedReadSeq;
    final refs = <CustodyWalRef>[];
    for (final r in state.checkpoint.ringRanges) {
      if (r.endSeq > from && r.startSeq < target) refs.addAll(r.wals);
    }
    for (final r in state.checkpoint.liveRanges) {
      if (r.endSeq > from && r.startSeq < target) refs.addAll(r.wals);
    }
    for (final w in refs) {
      final ok = await _walValidator(w);
      final s = _state(deviceId, epoch);
      if (s == null || !identical(s.sessionToken, token) || s.checkpoint.ringId != cpRingId) return null;
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
    if (current == null) return null;
    return current < target ? current : target;
  }

  Future<void> markAdvanced(String deviceId, int epoch, int seq, {int? markSeq}) async {
    final state = _state(deviceId, epoch);
    if (state == null) return;
    if (seq > state.checkpoint.lastAdvancedSeq) state.checkpoint.lastAdvancedSeq = seq;
    if (markSeq != null) state.checkpoint.lastAdvancedMarkSeq = markSeq;
    await _persist(state.checkpoint);
  }

  bool hasConnection(String deviceId, int epoch) => _state(deviceId, epoch)?.connected ?? false;

  bool isIncarnationInvalid(String deviceId, int epoch) => _state(deviceId, epoch)?.incarnationInvalid ?? false;

  int? latestEpoch(String deviceId) {
    final s = _devices[deviceId];
    return (s != null && s.connected) ? s.epoch : null;
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
    final cp = state.checkpoint;
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
      state.durableLiveChunks.clear();
      state.evidenceBroken = false;
      state.incarnationInvalid = false;
      state.ordinals = LivePacketOrdinals();
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
        final already = state.checkpoint.liveRanges.any((r) => r.startSeq == prev.ringSeq && r.endSeq == cur.ringSeq);
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
    for (final r in [...cp.liveRanges, ...cp.ringRanges]) {
      for (final w in (r is LiveRangeProof ? r.wals : (r as RingRangeProof).wals)) {
        if (!await _walValidator(w)) return false;
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
