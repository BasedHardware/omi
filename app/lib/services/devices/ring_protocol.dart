import 'dart:typed_data';

import 'package:omi/services/devices/connectors/device_connection.dart';

/// Pure-data helpers for the ring-buffer storage protocol (firmware 3.0.20+,
/// omi PR #7216). Kept free of BLE/connection state so they can be unit-tested.
///
/// Wire shapes (all multi-byte fields BE on the wire unless noted otherwise;
/// only the 16-byte status read uses LE because that's what the firmware
/// emits on the read characteristic).
///
///   Status read (storage_read_control char, 16 bytes, u32 LE x4):
///     [used_bytes][unread_packets][free_bytes][rtc_valid]
///
///   Notifications on the control char (one opcode byte + payload):
///     0x01 ACK         [0x01][status]
///     0x02 INFO        [0x02][read:u64][write:u64][cap:u32][dropped:u64][pkt_size:u16]
///     0x03 DATA        [0x03][raw_bytes...]   <-- not aligned to record boundaries
///     0x04 DONE        [0x04][status][next_seq:u64](optional [crc32:u32])
///     0x05 READ_BEGIN  [0x05][transfer_start_seq:u64][packet_count:u32]
///
///   Each ring record (packet_size = 444 bytes):
///     [timestamp:4 BE][audio_payload:440]
///   The 440-byte payload is packed [size:1][frame:size]... with zero padding.
class RingProtocol {
  static const int recordSize = 444;
  static const int timestampBytes = 4;
  static const int audioPayloadBytes = recordSize - timestampBytes;

  static const int notifyAck = 0x01;
  static const int notifyInfo = 0x02;
  static const int notifyData = 0x03;
  static const int notifyDone = 0x04;
  static const int notifyReadBegin = 0x05;

  static const int cmdInfo = 0x10;
  static const int cmdRead = 0x11;
  static const int cmdAdvance = 0x12;
  static const int cmdClear = 0x13;
  static const int cmdStop = 0x03;

  static const int statusOk = 0;
  static const int statusStorageNotReady = 9;
  static const int statusSequenceOutOfRange = 10;
  static const int statusStorageFailed = 11;

  /// Parse a two-byte ACK notification. Returns null for every other frame.
  static int? parseAckStatus(List<int> value) {
    if (value.length < 2 || value[0] != notifyAck) return null;
    return value[1];
  }

  /// Parse the 16-byte status read into a RingStatus. Returns null if the
  /// payload is too short.
  static RingStatus? parseStatus(List<int> value) {
    if (value.length < 16) return null;
    final bd = ByteData.sublistView(Uint8List.fromList(value));
    return RingStatus(
      usedBytes: bd.getUint32(0, Endian.little),
      unreadPackets: bd.getUint32(4, Endian.little),
      freeBytes: bd.getUint32(8, Endian.little),
      rtcValid: bd.getUint32(12, Endian.little),
    );
  }

  /// Parse a NOTIFY_INFO (0x02) notification into a RingInfo. Returns null if
  /// the leading opcode is wrong or the payload is truncated.
  static RingInfo? parseInfoNotification(List<int> value) {
    if (value.isEmpty || value[0] != notifyInfo || value.length < 31) return null;
    final bd = ByteData.sublistView(Uint8List.fromList(value));
    return RingInfo(
      readSeq: bd.getUint64(1, Endian.big),
      writeSeq: bd.getUint64(9, Endian.big),
      capacityPackets: bd.getUint32(17, Endian.big),
      droppedPackets: bd.getUint64(21, Endian.big),
      packetSize: bd.getUint16(29, Endian.big),
    );
  }

  /// Parse a NOTIFY_DONE (0x04) notification.
  /// Returns null if the leading opcode is wrong or the payload is truncated.
  static DoneNotification? parseDoneNotification(List<int> value) {
    if (value.isEmpty || value[0] != notifyDone || value.length < 10) return null;
    final bd = ByteData.sublistView(Uint8List.fromList(value));
    return DoneNotification(
      status: bd.getUint8(1),
      nextSeq: bd.getUint64(2, Endian.big),
      transferCrc32: value.length >= 14 ? bd.getUint32(10, Endian.big) : null,
    );
  }

  /// Parse a NOTIFY_READ_BEGIN (0x05) notification.
  static ReadBeginNotification? parseReadBeginNotification(List<int> value) {
    if (value.isEmpty || value[0] != notifyReadBegin || value.length < 13) return null;
    final bd = ByteData.sublistView(Uint8List.fromList(value));
    return ReadBeginNotification(
      transferStartSeq: bd.getUint64(1, Endian.big),
      packetCount: bd.getUint32(9, Endian.big),
    );
  }

  /// Encode CMD_RING_READ payload: [0x11][start_seq:u64 BE](+optional [count:u32 BE]).
  /// Pass [packetCount] = null or 0 to stream everything available.
  static Uint8List encodeReadCommand(int startSeq, {int? packetCount}) {
    final hasCount = packetCount != null && packetCount > 0;
    final cmd = ByteData(hasCount ? 13 : 9);
    cmd.setUint8(0, cmdRead);
    cmd.setUint64(1, startSeq, Endian.big);
    if (hasCount) {
      cmd.setUint32(9, packetCount, Endian.big);
    }
    return cmd.buffer.asUint8List();
  }

  /// Encode CMD_RING_ADVANCE payload: [0x12][new_read_seq:u64 BE].
  static Uint8List encodeAdvanceCommand(int newReadSeq) {
    final cmd = ByteData(9);
    cmd.setUint8(0, cmdAdvance);
    cmd.setUint64(1, newReadSeq, Endian.big);
    return cmd.buffer.asUint8List();
  }

  /// Read the 4-byte big-endian timestamp prefix of a ring record.
  /// Caller is responsible for supplying a buffer of at least 4 bytes.
  static int readRecordTimestamp(List<int> record) {
    return (record[0] << 24) | (record[1] << 16) | (record[2] << 8) | record[3];
  }

  /// Record timestamps survive a reboot where the device's current RTC-valid
  /// flag may be false. Trust plausible embedded capture time rather than
  /// collapsing old audio onto the retry time.
  static bool isPlausibleRecordTimestamp(
    int timestamp, {
    required int nowSeconds,
  }) {
    const earliestSupportedTimestamp = 1704067200;
    const maximumFutureSkewSeconds = 24 * 60 * 60;
    return timestamp >= earliestSupportedTimestamp && timestamp <= nowSeconds + maximumFutureSkewSeconds;
  }

  /// The pendant may discard records only after the complete transfer reached
  /// durable phone storage. A BLE TX completion or a partial stream is not an
  /// acknowledgement.
  static bool canAdvance({
    required bool reachedDone,
    required bool doneOk,
    required bool flushError,
    required bool isCancelled,
    required bool receivedCompleteRange,
    required bool protocolError,
    required bool crcVerified,
  }) {
    return reachedDone &&
        doneOk &&
        !flushError &&
        !isCancelled &&
        receivedCompleteRange &&
        !protocolError &&
        crcVerified;
  }

  /// Validate that READ_BEGIN, DATA, and DONE describe one complete contiguous
  /// record range. This catches missing notification bytes before a cumulative
  /// ADVANCE command could discard the corresponding SD records.
  static bool receivedCompleteRange({
    required int? transferStartSeq,
    required int? announcedPacketCount,
    required int? doneNextSeq,
    required int receivedPacketCount,
    required int pendingBytes,
  }) {
    if (transferStartSeq == null || announcedPacketCount == null || doneNextSeq == null) return false;
    return announcedPacketCount >= 0 &&
        doneNextSeq == transferStartSeq + announcedPacketCount &&
        receivedPacketCount == announcedPacketCount &&
        pendingBytes == 0;
  }

  /// Parse the 440-byte audio payload of a ring record into opus frames.
  /// Format: [size:1][frame:size]... with zero padding allowed at any point.
  /// A leading byte of 0 is a no-op padding marker; otherwise it is the
  /// length of the next frame.
  ///
  /// Boundary uses `>=` for compatibility with legacy 3.0.20 records. That
  /// firmware can flush a record after writing only a size marker at the exact
  /// boundary, leaving stale bytes where the frame would be. New firmware
  /// preserves this no-exact-fit wire invariant.
  static List<List<int>> parseAudioPayload(List<int> audio) {
    final frames = <List<int>>[];
    int offset = 0;
    while (offset < audio.length - 1) {
      final size = audio[offset];
      if (size == 0) {
        offset += 1;
        continue;
      }
      if (offset + 1 + size >= audio.length) {
        break;
      }
      frames.add(audio.sublist(offset + 1, offset + 1 + size));
      offset += size + 1;
    }
    return frames;
  }

  /// Parse the immutable source identity written by the ring recovery path.
  /// The half-open range is `[start, end)`.
  static ({int start, int end})? parseSourceRange(String? sourceId) {
    if (sourceId == null) return null;
    final match = RegExp(r'^ring_(\d+)_(\d+)$').firstMatch(sourceId);
    if (match == null) return null;
    final start = int.parse(match.group(1)!);
    final end = int.parse(match.group(2)!);
    if (end <= start) return null;
    return (start: start, end: end);
  }
}

/// In-memory index of ring ranges already durably represented on the phone.
///
/// This is sequence identity, not audio-content deduplication. It lets the app
/// fetch the live head before an old backlog, then advance the pendant only
/// when the historical gap closes.
class RingSequenceCoverage {
  final List<({int start, int end})> _ranges = [];

  RingSequenceCoverage([Iterable<({int start, int end})> ranges = const []]) {
    for (final range in ranges) {
      add(range.start, range.end);
    }
  }

  void add(int start, int end) {
    if (end <= start) return;
    var mergedStart = start;
    var mergedEnd = end;
    var index = 0;
    while (index < _ranges.length && _ranges[index].end < mergedStart) {
      index += 1;
    }
    while (index < _ranges.length && _ranges[index].start <= mergedEnd) {
      final range = _ranges.removeAt(index);
      if (range.start < mergedStart) mergedStart = range.start;
      if (range.end > mergedEnd) mergedEnd = range.end;
    }
    _ranges.insert(index, (start: mergedStart, end: mergedEnd));
  }

  /// Highest sequence covered without a gap beginning at [start].
  int contiguousEndFrom(int start) {
    var end = start;
    for (final range in _ranges) {
      if (range.end <= end) continue;
      if (range.start > end) break;
      end = range.end;
    }
    return end;
  }

  /// First covered range beginning at or after [start].
  ({int start, int end})? firstRangeAtOrAfter(int start) {
    for (final range in _ranges) {
      if (range.end <= start) continue;
      return range;
    }
    return null;
  }

  /// First uncovered sequence in `[start, end)`, or [end] if fully covered.
  int firstUncovered(int start, int end) {
    var cursor = start;
    for (final range in _ranges) {
      if (range.end <= cursor) continue;
      if (range.start > cursor) return cursor;
      if (range.end > cursor) cursor = range.end;
      if (cursor >= end) return end;
    }
    return cursor;
  }

  bool covers(int start, int end) => end <= contiguousEndFrom(start);

  List<({int start, int end})> get ranges => List.unmodifiable(_ranges);
}

class RingStorageException implements Exception {
  const RingStorageException(this.message);

  final String message;

  @override
  String toString() => message;
}

class RingCommandRejectedException extends RingStorageException {
  const RingCommandRejectedException({
    required this.command,
    required this.status,
  }) : super(
          status == RingProtocol.statusStorageNotReady
              ? 'Device storage is not ready'
              : status == RingProtocol.statusStorageFailed
                  ? 'Device storage needs attention'
                  : 'Device rejected $command (status $status)',
        );

  final String command;
  final int status;

  bool get isRetryable => status == RingProtocol.statusStorageNotReady;
}

class RingInfoUnavailableException extends RingStorageException {
  const RingInfoUnavailableException() : super('Device storage did not provide ring information');
}

/// Bounded retry for the ring snapshot handshake.
///
/// Firmware waits for its SD remount before replying, but a remount can finish
/// immediately after that deadline. Retry only the explicit retryable status
/// (or a missing response), and always stop after [maxAttempts].
class RingInfoRetryPolicy {
  const RingInfoRetryPolicy({
    this.maxAttempts = 3,
    this.backoff = const [Duration(milliseconds: 500), Duration(seconds: 1)],
  }) : assert(maxAttempts > 0);

  final int maxAttempts;
  final List<Duration> backoff;

  Future<RingInfo> run(
    Future<RingInfo?> Function() request, {
    Future<void> Function(Duration delay)? wait,
  }) async {
    final waitFor = wait ?? Future<void>.delayed;
    RingStorageException lastError = const RingInfoUnavailableException();

    for (var attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        final info = await request();
        if (info != null) return info;
        lastError = const RingInfoUnavailableException();
      } on RingCommandRejectedException catch (error) {
        if (!error.isRetryable) rethrow;
        lastError = error;
      }

      if (attempt + 1 < maxAttempts) {
        final delay = backoff.isEmpty ? Duration.zero : backoff[attempt.clamp(0, backoff.length - 1)];
        await waitFor(delay);
      }
    }

    throw lastError;
  }
}

/// Decoded NOTIFY_DONE payload.
class DoneNotification {
  final int status;
  final int nextSeq;
  final int? transferCrc32;

  const DoneNotification({
    required this.status,
    required this.nextSeq,
    this.transferCrc32,
  });

  bool get isOk => status == 0;
}

/// Incremental IEEE CRC-32 over raw NOTIFY_DATA payload bytes.
///
/// New firmware includes this value in DONE. Legacy 3.0.20 firmware omits it,
/// so callers verify when present while retaining read compatibility.
class RingTransferCrc32 {
  int _crc = 0xFFFFFFFF;

  void add(List<int> bytes) {
    for (final byte in bytes) {
      _crc ^= byte & 0xFF;
      for (var bit = 0; bit < 8; bit++) {
        _crc = (_crc & 1) != 0 ? (_crc >> 1) ^ 0xEDB88320 : _crc >> 1;
      }
    }
  }

  int get value => (_crc ^ 0xFFFFFFFF) & 0xFFFFFFFF;
}

/// Decoded NOTIFY_READ_BEGIN payload.
class ReadBeginNotification {
  final int transferStartSeq;
  final int packetCount;

  const ReadBeginNotification({
    required this.transferStartSeq,
    required this.packetCount,
  });
}

/// Reassembles unaligned NOTIFY_DATA byte chunks into 444-byte ring records.
/// Internal buffer holds bytes that don't yet form a full record. Call
/// [append] for each NOTIFY_DATA payload (with the 0x03 opcode already
/// stripped); call [drainRecords] to pull complete records.
class RingRecordReassembler {
  final List<int> _buffer = [];

  void append(List<int> bytes) {
    _buffer.addAll(bytes);
  }

  /// Pop and return all complete 444-byte records currently buffered.
  /// Leftover (incomplete) bytes remain in the buffer for the next append.
  List<Uint8List> drainRecords() {
    final out = <Uint8List>[];
    while (_buffer.length >= RingProtocol.recordSize) {
      out.add(Uint8List.fromList(_buffer.sublist(0, RingProtocol.recordSize)));
      _buffer.removeRange(0, RingProtocol.recordSize);
    }
    return out;
  }

  int get pendingBytes => _buffer.length;
}
