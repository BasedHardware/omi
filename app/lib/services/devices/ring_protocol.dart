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
///     0x04 DONE        [0x04][status][next_seq:u64]
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
  static const int notifyLiveMark = 0x06;

  static const int cmdInfo = 0x10;
  static const int cmdRead = 0x11;
  static const int cmdAdvance = 0x12;
  static const int cmdClear = 0x13;
  static const int cmdCustodyEnable = 0x14;
  static const int cmdAdvanceId = 0x15;
  static const int cmdStop = 0x03;

  static const int ackOk = 0;
  static const int ackInvalidCommand = 6;
  static const int ackSeqOutOfRange = 10;
  static const int ackRingIdMismatch = 11;

  static const int capAppAckReclaim = 0x01;
  static const int capLivePersist = 0x02;
  static const int capAdvanceIdempotent = 0x04;
  static const int capRingId = 0x08;
  static const int capMaskV1 = 0x0F;
  static const int custodyContractVersion = 1;

  static bool isRingBufferFirmware(String? version) {
    if (version == null || version.isEmpty || version == 'Unknown') return false;
    final parts = version.split('.').map((p) => int.tryParse(p) ?? 0).toList();
    if (parts.length < 3) return false;
    if (parts[0] > 3) return true;
    if (parts[0] < 3) return false;
    if (parts[1] > 0) return true;
    if (parts[1] < 0) return false;
    return parts[2] >= 20;
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
      advertisedCaps: value.length >= 32 ? bd.getUint8(31) : 0,
      contractVersion: value.length >= 33 ? bd.getUint8(32) : 0,
      ringId: value.length >= 41 ? bd.getUint64(33, Endian.big) : null,
      infoBytes: value.length,
    );
  }

  static LiveMarkNotification? parseLiveMarkNotification(List<int> value) {
    if (value.isEmpty || value[0] != notifyLiveMark || value.length < 19) return null;
    final bd = ByteData.sublistView(Uint8List.fromList(value));
    return LiveMarkNotification(
      ringId: bd.getUint64(1, Endian.big),
      ringSeq: bd.getUint64(9, Endian.big),
      liveIndex: bd.getUint16(17, Endian.big),
    );
  }

  /// Parse a NOTIFY_DONE (0x04) notification.
  /// Returns null if the leading opcode is wrong or the payload is truncated.
  static DoneNotification? parseDoneNotification(List<int> value) {
    if (value.isEmpty || value[0] != notifyDone || value.length < 10) return null;
    final bd = ByteData.sublistView(Uint8List.fromList(value));
    return DoneNotification(status: bd.getUint8(1), nextSeq: bd.getUint64(2, Endian.big));
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

  static Uint8List encodeCustodyEnableCommand(int requestedCaps) {
    final cmd = ByteData(3);
    cmd.setUint8(0, cmdCustodyEnable);
    cmd.setUint8(1, custodyContractVersion);
    cmd.setUint8(2, requestedCaps & 0xFF);
    return cmd.buffer.asUint8List();
  }

  static Uint8List encodeAdvanceIdCommand(int ringId, int newReadSeq) {
    final cmd = ByteData(17);
    cmd.setUint8(0, cmdAdvanceId);
    cmd.setUint64(1, ringId, Endian.big);
    cmd.setUint64(9, newReadSeq, Endian.big);
    return cmd.buffer.asUint8List();
  }

  /// Bit 31 of a record timestamp marks seconds since device boot, not epoch UTC
  /// (custody firmware writes it when the RTC is unset). Legacy firmware never sets it.
  static const int recordTimestampUptimeFlag = 0x80000000;

  /// Read the 4-byte big-endian timestamp prefix of a ring record as epoch seconds,
  /// or 0 (no usable time) when the record carries the uptime flag.
  /// Caller is responsible for supplying a buffer of at least 4 bytes.
  static int readRecordTimestamp(List<int> record) {
    final raw = (record[0] << 24) | (record[1] << 16) | (record[2] << 8) | record[3];
    return raw & recordTimestampUptimeFlag != 0 ? 0 : raw;
  }

  /// Parse the 440-byte audio payload of a ring record into opus frames.
  /// Format: [size:1][frame:size]... with zero padding allowed at any point.
  /// A leading byte of 0 is a no-op padding marker; otherwise it is the
  /// length of the next frame.
  ///
  /// Boundary uses `>=` to match the firmware's overflow rule in
  /// transport.c:write_to_storage — at the boundary the firmware writes a
  /// trailing size byte without its frame (the frame goes to the next 440B
  /// block); the bytes after it are stale and must not be parsed.
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
}

class LiveMarkNotification {
  final int ringId;
  final int ringSeq;
  final int liveIndex;

  const LiveMarkNotification({required this.ringId, required this.ringSeq, required this.liveIndex});

  @override
  String toString() => 'LiveMarkNotification(ring=$ringId, seq=$ringSeq, liveIndex=$liveIndex)';
}

/// Decoded NOTIFY_DONE payload.
class DoneNotification {
  final int status;
  final int nextSeq;

  const DoneNotification({required this.status, required this.nextSeq});

  bool get isOk => status == 0;
}

/// Decoded NOTIFY_READ_BEGIN payload.
class ReadBeginNotification {
  final int transferStartSeq;
  final int packetCount;

  const ReadBeginNotification({required this.transferStartSeq, required this.packetCount});
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
