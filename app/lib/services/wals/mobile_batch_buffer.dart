import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'dart:io';
import 'dart:typed_data';

import 'package:uuid/uuid.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/batch_ring_proof.dart';
import 'package:omi/services/wals/wal_frame_encoder.dart';

/// A recoverable append journal in the EXISTING WAL wire format. All captured
/// frames, including silence, are written before routing can suppress live send.
/// A sidecar precedes the first write; restart scans it even if the WAL index
/// update was interrupted. Sealed files use the normal sync/retry/job pipeline.
class MobileBatchBuffer {
  MobileBatchBuffer(
      {required this.directory,
      required this.publish,
      this.onSealed,
      this.onPublishFailed,
      this.maxBytes = 256 * 1024 * 1024,
      this.maxFiles = 4096,
      RandomAccessFile Function(File)? openWriter})
      : _openWriter = openWriter ?? _openAppend;

  static RandomAccessFile _openAppend(File file) => file.openSync(mode: FileMode.append);

  static const defaultMaxFileSeconds = 60;

  /// Longest file this buffer writes before sealing it. Applies from the next
  /// frame, so an open file longer than a newly lowered cap seals at once.
  int get maxFileSeconds => _maxFileSeconds;
  int _maxFileSeconds = defaultMaxFileSeconds;
  set maxFileSeconds(int seconds) {
    if (seconds > 0 && seconds <= defaultMaxFileSeconds) _maxFileSeconds = seconds;
  }

  /// [maxFiles] counts files at the default length. A shorter cap writes
  /// proportionally more files for the same audio, so the limit scales with it
  /// and the buffer admits the same span of capture either way.
  int get _fileLimit => maxFiles * defaultMaxFileSeconds ~/ _maxFileSeconds;

  // One process-wide revision also covers observers recreated for the same
  // directory. It invalidates disk snapshots, never supplies custody proof.
  static int _journalRevision = 0;
  static int get journalRevision => _journalRevision;

  final Directory directory;
  final Future<void> Function(Wal) publish;
  final void Function(Wal)? onSealed;
  final void Function(Wal)? onPublishFailed;
  final int maxBytes;
  final int maxFiles;
  final RandomAccessFile Function(File) _openWriter;
  RandomAccessFile? _writer;
  Wal? _wal;
  File? _journal;
  BatchLiveContext? _liveContext;
  int _bytes = 0;
  int _chunkFrames = 0;
  int _files = 0;
  Future<void> _pending = Future.value();
  bool failed = false;

  /// Read durable journals, including failed seals and prior processes. A
  /// recovered journal may overlap the index: over-count until acceptance,
  /// never discard evidence because an in-memory writer/list lost its WAL.
  /// Unreadable metadata counts conservatively; a directory error propagates
  /// so the reporter omits the marker instead of asserting zero. No writes.
  /// With [ownerUid], a journal that names another account is not this
  /// account's pending audio: it can never be uploaded from here, so counting
  /// it would hold the recording open forever after an account switch.
  Future<int> pendingJournalCount(String recordingSessionId,
      {String? ownerUid, DateTime? through, DateTime? now, Map<String, int> acceptedFileBytes = const {}}) async {
    var count = 0;
    final throughSeconds = through?.millisecondsSinceEpoch;
    final nowSeconds = (now ?? DateTime.now()).millisecondsSinceEpoch ~/ 1000;
    await for (final entry in directory.list(followLinks: false)) {
      if (!entry.path.endsWith('.batch-journal')) continue;
      if (entry is! File) {
        count++; // A link or unreadable entry cannot prove absence of audio.
        continue;
      }
      final name = entry.uri.pathSegments.last;
      final audioName = name.substring(0, name.length - '.batch-journal'.length);
      try {
        final acceptedBytes = acceptedFileBytes[audioName];
        // Replay can expose an open journal before its writer seals. A later
        // append is pending even if the server accepted an earlier prefix.
        if (acceptedBytes != null &&
            await File('${directory.path}/$audioName').length() == acceptedBytes &&
            !await File('${directory.path}/$audioName.torn').exists()) {
          continue;
        }
        final metadata = jsonDecode(await entry.readAsString());
        if (metadata is! Map<String, dynamic> ||
            metadata['owner_uid'] is! String ||
            (metadata['owner_uid'] as String).isEmpty ||
            metadata['recording_session_id'] is! String ||
            (metadata['recording_session_id'] as String).isEmpty ||
            metadata['timer_start'] is! int) {
          count++; // Retained evidence cannot prove this recording has nothing left.
          continue;
        }
        if (metadata['recording_session_id'] != recordingSessionId) continue;
        if (ownerUid != null && ownerUid.isNotEmpty && metadata['owner_uid'] != ownerUid) continue;
        final start = metadata['timer_start'] as int;
        if (throughSeconds == null || start <= 0 || start <= throughSeconds ~/ 1000 || start > nowSeconds) count++;
      } on FileSystemException {
        count++;
      } on FormatException {
        count++;
      }
    }
    return count;
  }

  Future<void> initialize() async {
    await directory.create(recursive: true);
    _files = directory.listSync().whereType<File>().where((f) => _isRetainedBatchAudio(f.path)).length;
    _bytes = directory.listSync().whereType<File>().where((f) => _isRetainedBatchAudio(f.path)).fold<int>(
          0,
          (sum, f) => sum + f.lengthSync(),
        );
  }

  /// Synchronous ownership boundary: true means these bytes belong ONLY to
  /// batch; false means the caller retains the ordinary live/WAL path.
  bool append(
    List<int> payload, {
    required String uid,
    required BleAudioCodec codec,
    required DateTime now,
    Geolocation? geolocation,
    String? recordingSessionId,
    BatchLiveContext? liveContext,
    int? Function()? observeLiveOrdinal,
  }) {
    if (failed ||
        (_writer == null && _files >= _fileLimit) ||
        uid.isEmpty ||
        !codec.isOpusSupported() ||
        _bytes + payload.length + 4 > maxBytes) {
      return false;
    }
    if (!batchRingProofEnabled) liveContext = null;
    var accepted = false;
    _journalRevision++;
    try {
      if (_wal != null &&
          (_wal!.ownerUid != uid ||
              _wal!.codec != codec ||
              _wal!.recordingSessionId != recordingSessionId ||
              _liveContext != liveContext)) {
        seal();
      }
      if (_writer == null) {
        // A codec/origin change can seal an existing writer above.
        if (_files >= _fileLimit) return false;
        final token = const Uuid().v4().replaceAll('-', '');
        final start = now.microsecondsSinceEpoch / 1000000;
        final name = 'audio_omimobilebatch${token}_${codec}_16000_1_fs${codec.getFrameSize()}_$start.bin';
        final wal = Wal(
          timerStart: start.floor(),
          seconds: 0,
          codec: codec,
          sampleRate: 16000,
          channel: 1,
          storage: WalStorage.disk,
          status: WalStatus.miss,
          filePath: name,
          device: 'omimobilebatch$token',
          deviceModel: 'Omi',
          ownerUid: uid,
          geolocation: geolocation,
          recordingSessionId: recordingSessionId,
        );
        _journal = File('${directory.path}/$name.batch-journal');
        _journal!.writeAsStringSync(jsonEncode(wal.toJson()), flush: true);
        _writer = _openWriter(File('${directory.path}/$name'));
        _files++;
        _wal = wal;
        _chunkFrames = 0;
        _liveContext = liveContext;
      }
      final bytes = encodeWalFrames([payload]);
      _writer!.writeFromSync(bytes);
      accepted = true;
      // OS-visible writes survive process kill; periodic fsync also bounds
      // power-loss exposure to one second. Seal always fsyncs before publish.
      _bytes += bytes.length;
      _chunkFrames++;
      _wal!.totalFrames = _chunkFrames;
      _wal!.seconds = (_chunkFrames / codec.getFramesPerSecond()).ceil();
      _wal!.storageTotalBytes += bytes.length;
      if (liveContext != null) {
        final ordinal = observeLiveOrdinal?.call();
        final wal = _wal!;
        if (_chunkFrames == 1 && ordinal != null) {
          wal.liveRingId = liveContext.ringId;
          wal.liveOrdinalStart = ordinal;
          wal.liveOrdinalEnd = ordinal + 1;
          wal.batchLiveSession = liveContext.sessionId;
          wal.liveDeviceId = liveContext.deviceId;
        } else if (ordinal != null && wal.liveOrdinalEnd == ordinal && wal.batchLiveSession == liveContext.sessionId) {
          wal.liveOrdinalEnd = ordinal + 1;
        } else {
          // Do not bridge a missing, reordered or fragmented packet.
          wal.liveRingId = null;
          wal.liveOrdinalStart = null;
          wal.liveOrdinalEnd = null;
          wal.batchLiveSession = null;
          wal.liveDeviceId = null;
        }
      }
      if (_chunkFrames % codec.getFramesPerSecond() == 0) {
        _writer!.flushSync();
        if (liveContext != null) _checkpointJournal();
      }
      if (_chunkFrames >= codec.getFramesPerSecond() * _maxFileSeconds) seal();
      return true;
    } on FileSystemException {
      failed = true;
      // The journal retains any complete writes for startup recovery.
      try {
        _writer?.closeSync();
      } on FileSystemException {/* journal retains bytes */}
      _writer = null;
      _wal = null;
      return accepted;
    }
  }

  void _checkpointJournal() {
    final journal = _journal!;
    // Freeze the exact fsynced prefix before the writer can append again.
    // Serial async metadata I/O avoids blocking the UI isolate and precedes
    // seal publication in the same queue. An interrupted snapshot keeps the
    // previous conservative prefix; it never supplies reclaim authority.
    final snapshot = _wal!.toJson();
    final audio = File('${directory.path}/${_wal!.filePath}');
    final prefixBytes = _wal!.storageTotalBytes;
    _pending = _pending.then((_) async {
      final tmp = File('${journal.path}.tmp');
      snapshot['file_sha256'] = (await sha256.bind(audio.openRead(0, prefixBytes)).first).toString();
      await tmp.writeAsString(jsonEncode(snapshot), flush: true);
      await tmp.rename(journal.path);
    }).catchError((Object _) {
      failed = true;
    });
  }

  void seal() {
    final writer = _writer, wal = _wal, journal = _journal;
    if (writer == null || wal == null || journal == null) return;
    try {
      writer.flushSync();
      if (_liveContext != null) _checkpointJournal();
      writer.closeSync();
    } on FileSystemException {
      failed = true;
      try {
        writer.closeSync();
      } on FileSystemException {/* journal retains bytes */}
      _writer = null;
      _wal = null;
      _journal = null;
      return;
    }
    _writer = null;
    _wal = null;
    _journal = null;
    onSealed?.call(wal);
    var published = false;
    _pending = _pending.then((_) async {
      wal.fileSha256 = (await sha256.bind(File('${directory.path}/${wal.filePath}').openRead()).first).toString();
      if (wal.mobileBatchHold != null) {
        try {
          final tmp = File('${journal.path}.tmp');
          await tmp.writeAsString(jsonEncode(wal.toJson()), flush: true);
          await tmp.rename(journal.path);
        } on FileSystemException {
          // The existing journal still protects the audio. The index can
          // carry the hold stamp even if this optional checkpoint failed.
        }
      }
      await publish(wal);
      published = true;
      // publish persists the shared WAL index before removing the journal.
      if (await journal.exists()) await journal.delete();
    }).catchError((Object _) {
      // Keep journal + bytes for recovery, and return to the live path.
      failed = true;
      if (!published) onPublishFailed?.call(wal);
    });
  }

  Future<void> close() async {
    seal();
    await _pending;
  }

  Future<void> get pending => _pending;
  bool get hasFrames => _writer != null;

  // Torn originals are kept for recovery/export and share the same budget.
  static bool _isRetainedBatchAudio(String path) =>
      _isBatchAudio(path) || (path.endsWith('.torn') && _isBatchAudio(path.substring(0, path.length - 5)));

  static bool _isBatchAudio(String path) =>
      path.split('/').last.startsWith('audio_omimobilebatch') && path.endsWith('.bin');

  /// Recover only unindexed journals. Never resurrect a completed/indexed WAL
  /// or cross ownership: the existing loader subsequently partitions by uid.
  static Future<List<Wal>> recover(Directory directory, List<Wal> indexed) async {
    final result = List<Wal>.of(indexed);
    if (!await directory.exists()) return result;
    final known = indexed.map((wal) => wal.filePath?.split('/').last).toSet();
    await for (final entry in directory.list()) {
      if (entry is! File || !entry.path.endsWith('.batch-journal')) continue;
      try {
        final metadata = jsonDecode(await entry.readAsString());
        if (metadata is! Map<String, dynamic> ||
            metadata['owner_uid'] is! String ||
            (metadata['owner_uid'] as String).isEmpty ||
            metadata['timer_start'] is! int ||
            metadata['codec'] is! String) {
          continue;
        }
        final wal = Wal.fromJson(metadata);
        final name = wal.filePath;
        if (name == null || name.contains('/') || !_isBatchAudio(name) || !wal.codec.isOpusSupported()) continue;
        if (known.contains(name)) continue;
        final audio = File('${directory.path}/$name');
        if (!await audio.exists()) continue;
        final bytes = await audio.readAsBytes();
        final header = ByteData.sublistView(bytes);
        final claimedFrames = wal.totalFrames;
        final claimedBytes = wal.storageTotalBytes;
        var claimedPrefixBytes = 0;
        var offset = 0, frames = 0;
        while (offset + 4 <= bytes.length) {
          final length = header.getUint32(offset, Endian.little);
          if (length == 0 || length > 1275 || offset + 4 + length > bytes.length) break;
          offset += 4 + length;
          frames++;
          if (frames == claimedFrames) claimedPrefixBytes = offset;
        }
        if (frames == 0) continue;
        if (offset != bytes.length) {
          // Preserve the original torn tail for recovery/export before repair.
          await audio.copy('${audio.path}.torn');
          final repair = await audio.open(mode: FileMode.append);
          await repair.truncate(offset);
          await repair.close();
        }
        // A snapshot can prove only its original complete prefix. Additional
        // on-disk frames are recovered but never given inferred ordinals.
        if (!batchRingProofEnabled ||
            wal.fileSha256 == null ||
            claimedBytes > bytes.length ||
            sha256.convert(bytes.sublist(0, claimedBytes)).toString() != wal.fileSha256 ||
            wal.batchLiveSession == null ||
            wal.liveOrdinalStart == null ||
            wal.liveOrdinalEnd == null ||
            wal.liveOrdinalEnd! - wal.liveOrdinalStart! != claimedFrames ||
            claimedFrames <= 0 ||
            claimedFrames > frames ||
            claimedPrefixBytes != claimedBytes) {
          wal.liveRingId = null;
          wal.liveOrdinalStart = null;
          wal.liveOrdinalEnd = null;
          wal.batchLiveSession = null;
          wal.liveDeviceId = null;
        }
        // A process-kill-visible write is not yet durable custody. This fsync
        // precedes admission of the recovered entry into the shared index.
        final durable = await audio.open(mode: FileMode.append);
        try {
          await durable.flush();
        } finally {
          await durable.close();
        }
        wal.fileSha256 = sha256.convert(bytes.sublist(0, offset)).toString();
        wal.recoveredBatchJournal = true;
        wal.totalFrames = frames;
        wal.seconds = (frames / wal.codec.getFramesPerSecond()).ceil();
        wal.storageTotalBytes = offset;
        wal.status = WalStatus.miss;
        wal.storage = WalStorage.disk;
        result.add(wal);
        known.add(name);
      } on FileSystemException {
        // Preserve the journal; a later launch can retry the same recovery.
      } on FormatException {
        // Unreadable metadata remains available, never guessed into an owner.
      } on TypeError {
        // Invalid optional fields cannot strand other recoverable recordings.
      }
    }
    return result;
  }
}
