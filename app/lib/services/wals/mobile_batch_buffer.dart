import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:uuid/uuid.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_frame_encoder.dart';

/// A recoverable append journal in the EXISTING WAL wire format. All captured
/// frames, including silence, are written before routing can suppress live send.
/// A sidecar precedes the first write; restart scans it even if the WAL index
/// update was interrupted. Sealed files use the normal sync/retry/job pipeline.
class MobileBatchBuffer {
  MobileBatchBuffer(
      {required this.directory, required this.publish, this.maxBytes = 256 * 1024 * 1024, this.maxFiles = 4096});

  final Directory directory;
  final Future<void> Function(Wal) publish;
  final int maxBytes;
  final int maxFiles;
  RandomAccessFile? _writer;
  Wal? _wal;
  File? _journal;
  int _bytes = 0;
  int _chunkFrames = 0;
  int _files = 0;
  Future<void> _pending = Future.value();
  bool failed = false;

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
  }) {
    if (failed ||
        (_writer == null && _files >= maxFiles) ||
        uid.isEmpty ||
        !codec.isOpusSupported() ||
        _bytes + payload.length + 4 > maxBytes) {
      return false;
    }
    var accepted = false;
    try {
      if (_wal != null &&
          (_wal!.ownerUid != uid || _wal!.codec != codec || _wal!.recordingSessionId != recordingSessionId)) {
        seal();
      }
      if (_writer == null) {
        // A codec/origin change can seal an existing writer above.
        if (_files >= maxFiles) return false;
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
        _writer = File('${directory.path}/$name').openSync(mode: FileMode.append);
        _files++;
        _wal = wal;
        _chunkFrames = 0;
      }
      final bytes = encodeWalFrames([payload]);
      _writer!.writeFromSync(bytes);
      accepted = true;
      // OS-visible writes survive process kill; periodic fsync also bounds
      // power-loss exposure to one second. Seal always fsyncs before publish.
      _bytes += bytes.length;
      _chunkFrames++;
      if (_chunkFrames % codec.getFramesPerSecond() == 0) _writer!.flushSync();
      _wal!.totalFrames = _chunkFrames;
      _wal!.seconds = (_chunkFrames / codec.getFramesPerSecond()).ceil();
      _wal!.storageTotalBytes += bytes.length;
      if (_chunkFrames >= codec.getFramesPerSecond() * 60) seal();
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

  void seal() {
    final writer = _writer, wal = _wal, journal = _journal;
    if (writer == null || wal == null || journal == null) return;
    try {
      writer.flushSync();
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
    _pending = _pending.then((_) async {
      await publish(wal);
      // publish persists the shared WAL index before removing the journal.
      if (await journal.exists()) await journal.delete();
    }).catchError((Object _) {
      // Keep journal + bytes for recovery, and return to the live path.
      failed = true;
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
        var offset = 0, frames = 0;
        while (offset + 4 <= bytes.length) {
          final length = header.getUint32(offset, Endian.little);
          if (length == 0 || length > 1275 || offset + 4 + length > bytes.length) break;
          offset += 4 + length;
          frames++;
        }
        if (frames == 0) continue;
        if (offset != bytes.length) {
          // Preserve the original torn tail for recovery/export before repair.
          await audio.copy('${audio.path}.torn');
          final repair = await audio.open(mode: FileMode.append);
          await repair.truncate(offset);
          await repair.close();
        }
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
