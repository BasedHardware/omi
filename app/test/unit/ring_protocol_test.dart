import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';

void main() {
  group('RingProtocol.parseStatus', () {
    test('decodes 16-byte status with four LE u32 fields', () {
      // used=1234, unread=42, free=99999, rtcValid=1
      final bytes = ByteData(16)
        ..setUint32(0, 1234, Endian.little)
        ..setUint32(4, 42, Endian.little)
        ..setUint32(8, 99999, Endian.little)
        ..setUint32(12, 1, Endian.little);
      final status = RingProtocol.parseStatus(bytes.buffer.asUint8List());
      expect(status, isNotNull);
      expect(status!.usedBytes, 1234);
      expect(status.unreadPackets, 42);
      expect(status.freeBytes, 99999);
      expect(status.rtcValid, 1);
      expect(status.isRtcValid, isTrue);
    });

    test('rtcValid=0 surfaces as isRtcValid=false', () {
      final bytes = ByteData(16)
        ..setUint32(0, 0, Endian.little)
        ..setUint32(4, 0, Endian.little)
        ..setUint32(8, 0, Endian.little)
        ..setUint32(12, 0, Endian.little);
      final status = RingProtocol.parseStatus(bytes.buffer.asUint8List())!;
      expect(status.isRtcValid, isFalse);
    });

    test('returns null for short payload', () {
      expect(RingProtocol.parseStatus([0, 1, 2, 3]), isNull);
      expect(RingProtocol.parseStatus(<int>[]), isNull);
    });
  });

  group('RingProtocol.parseInfoNotification', () {
    test('decodes a full 31-byte NOTIFY_INFO frame', () {
      // [0x02][read:u64 BE][write:u64 BE][cap:u32 BE][dropped:u64 BE][pkt_size:u16 BE]
      final bd = ByteData(31)
        ..setUint8(0, 0x02)
        ..setUint64(1, 1000, Endian.big)
        ..setUint64(9, 1500, Endian.big)
        ..setUint32(17, 4096, Endian.big)
        ..setUint64(21, 7, Endian.big)
        ..setUint16(29, 444, Endian.big);
      final info = RingProtocol.parseInfoNotification(bd.buffer.asUint8List());
      expect(info, isNotNull);
      expect(info!.readSeq, 1000);
      expect(info.writeSeq, 1500);
      expect(info.capacityPackets, 4096);
      expect(info.droppedPackets, 7);
      expect(info.packetSize, 444);
      expect(info.unreadPackets, 500);
    });

    test('returns null when the leading opcode is not 0x02', () {
      final bd = ByteData(31)..setUint8(0, 0x03);
      expect(RingProtocol.parseInfoNotification(bd.buffer.asUint8List()), isNull);
    });

    test('returns null for truncated payload', () {
      final bd = ByteData(20)..setUint8(0, 0x02);
      expect(RingProtocol.parseInfoNotification(bd.buffer.asUint8List()), isNull);
    });
  });

  group('RingProtocol.parseDoneNotification', () {
    test('decodes status + next_seq', () {
      final bd = ByteData(10)
        ..setUint8(0, 0x04)
        ..setUint8(1, 0)
        ..setUint64(2, 12345, Endian.big);
      final done = RingProtocol.parseDoneNotification(bd.buffer.asUint8List())!;
      expect(done.status, 0);
      expect(done.nextSeq, 12345);
      expect(done.isOk, isTrue);
    });

    test('non-zero status surfaces as isOk=false', () {
      final bd = ByteData(10)
        ..setUint8(0, 0x04)
        ..setUint8(1, 6)
        ..setUint64(2, 0, Endian.big);
      final done = RingProtocol.parseDoneNotification(bd.buffer.asUint8List())!;
      expect(done.isOk, isFalse);
    });

    test('returns null for truncated payload', () {
      expect(RingProtocol.parseDoneNotification([0x04, 0]), isNull);
    });
  });

  group('RingProtocol.parseReadBeginNotification', () {
    test('decodes start_seq + count', () {
      final bd = ByteData(13)
        ..setUint8(0, 0x05)
        ..setUint64(1, 999, Endian.big)
        ..setUint32(9, 50, Endian.big);
      final begin = RingProtocol.parseReadBeginNotification(bd.buffer.asUint8List())!;
      expect(begin.transferStartSeq, 999);
      expect(begin.packetCount, 50);
    });

    test('returns null for truncated payload', () {
      expect(RingProtocol.parseReadBeginNotification([0x05, 0, 0, 0, 0, 0, 0]), isNull);
    });
  });

  group('RingProtocol.encodeReadCommand', () {
    test('without count produces 9 bytes: [0x11][seq:u64 BE]', () {
      final bytes = RingProtocol.encodeReadCommand(0x0123456789ABCDEF);
      expect(bytes.length, 9);
      expect(bytes[0], 0x11);
      // u64 BE: 01 23 45 67 89 AB CD EF
      expect(bytes.sublist(1).toList(), [0x01, 0x23, 0x45, 0x67, 0x89, 0xAB, 0xCD, 0xEF]);
    });

    test('with positive count produces 13 bytes: [0x11][seq:u64 BE][count:u32 BE]', () {
      final bytes = RingProtocol.encodeReadCommand(1, packetCount: 100);
      expect(bytes.length, 13);
      expect(bytes[0], 0x11);
      // count u32 BE 100 = 00 00 00 64
      expect(bytes.sublist(9).toList(), [0x00, 0x00, 0x00, 0x64]);
    });

    test('count of 0 omits the count field (stream all)', () {
      final bytes = RingProtocol.encodeReadCommand(0, packetCount: 0);
      expect(bytes.length, 9);
    });

    test('null count omits the count field (stream all)', () {
      final bytes = RingProtocol.encodeReadCommand(0);
      expect(bytes.length, 9);
    });
  });

  group('RingProtocol.encodeAdvanceCommand', () {
    test('produces 9 bytes: [0x12][seq:u64 BE]', () {
      final bytes = RingProtocol.encodeAdvanceCommand(0xCAFEBABE);
      expect(bytes.length, 9);
      expect(bytes[0], 0x12);
      // 0xCAFEBABE as u64 BE = 00 00 00 00 CA FE BA BE
      expect(bytes.sublist(1).toList(), [0x00, 0x00, 0x00, 0x00, 0xCA, 0xFE, 0xBA, 0xBE]);
    });
  });

  group('RingProtocol.readRecordTimestamp', () {
    test('reads 4-byte big-endian timestamp prefix', () {
      // 0x6824B5C0 = epoch 2026-05-13 21:47:12 UTC
      const ts = 0x6824B5C0;
      final record = [0x68, 0x24, 0xB5, 0xC0, ...List.filled(440, 0)];
      expect(RingProtocol.readRecordTimestamp(record), ts);
    });

    test('reads 0 timestamp (rtc-invalid sentinel)', () {
      final record = [0, 0, 0, 0, ...List.filled(440, 0)];
      expect(RingProtocol.readRecordTimestamp(record), 0);
    });
  });

  group('RingProtocol.parseAudioPayload', () {
    test('parses a single packed frame', () {
      // [size=3][0xAA, 0xBB, 0xCC] then padding zeros
      final audio = <int>[3, 0xAA, 0xBB, 0xCC, ...List.filled(436, 0)];
      final frames = RingProtocol.parseAudioPayload(audio);
      expect(frames.length, 1);
      expect(frames[0], [0xAA, 0xBB, 0xCC]);
    });

    test('parses multiple packed frames', () {
      // Two 80-byte frames (typical opus). [80][80B][80][80B] then padding.
      final f1 = List<int>.generate(80, (i) => 0xB0 + (i & 0x0F));
      final f2 = List<int>.generate(80, (i) => 0xC0 + (i & 0x0F));
      final audio = <int>[80, ...f1, 80, ...f2];
      audio.addAll(List.filled(440 - audio.length, 0));
      final frames = RingProtocol.parseAudioPayload(audio);
      expect(frames.length, 2);
      expect(frames[0], f1);
      expect(frames[1], f2);
    });

    test('skips zero-byte padding markers between frames', () {
      // [size=2][0x01,0x02][0][size=2][0x03,0x04]
      final audio = <int>[2, 0x01, 0x02, 0, 2, 0x03, 0x04, ...List.filled(440 - 7, 0)];
      final frames = RingProtocol.parseAudioPayload(audio);
      expect(frames.length, 2);
      expect(frames[0], [0x01, 0x02]);
      expect(frames[1], [0x03, 0x04]);
    });

    test('stops when declared frame size would overrun the buffer', () {
      // [size=2][0x01,0x02][size=100, but only 2 bytes follow] — second frame
      // is truncated: 100 bytes won't fit, so the parser must drop it and stop.
      final audio = <int>[2, 0x01, 0x02, 100, 0xAA, 0xBB];
      final frames = RingProtocol.parseAudioPayload(audio);
      expect(frames.length, 1);
      expect(frames[0], [0x01, 0x02]);
    });

    test('returns empty for all-zero payload', () {
      final frames = RingProtocol.parseAudioPayload(List.filled(440, 0));
      expect(frames, isEmpty);
    });

    test('parses a frame that exactly fills the buffer (boundary)', () {
      // [size=2][0xAA, 0xBB] — buffer length 3, frame ends at last byte.
      // Boundary check must be > (not >=) for this to parse.
      final frames = RingProtocol.parseAudioPayload([2, 0xAA, 0xBB]);
      expect(frames.length, 1);
      expect(frames[0], [0xAA, 0xBB]);
    });

    test('parses tightly-packed frames with no trailing padding (440B exactly)', () {
      // 40 frames of [size=10][10B] = 40 * 11 = 440 bytes — the last frame
      // ends precisely at audio.length. With >=, the last frame is silently
      // dropped; with > it's preserved.
      final audio = <int>[];
      for (int i = 0; i < 40; i++) {
        audio.add(10);
        audio.addAll(List.filled(10, i & 0xFF));
      }
      expect(audio.length, 440);
      final frames = RingProtocol.parseAudioPayload(audio);
      expect(frames.length, 40);
      expect(frames.last, List.filled(10, 39 & 0xFF));
    });
  });

  group('RingRecordReassembler', () {
    test('produces no records until 444 bytes accumulate', () {
      final r = RingRecordReassembler();
      r.append(List.filled(200, 0xAA));
      expect(r.drainRecords(), isEmpty);
      expect(r.pendingBytes, 200);
      r.append(List.filled(243, 0xBB));
      expect(r.drainRecords(), isEmpty);
      expect(r.pendingBytes, 443);
    });

    test('emits exactly one record at the 444B boundary', () {
      final r = RingRecordReassembler();
      r.append(List.filled(444, 0x42));
      final records = r.drainRecords();
      expect(records.length, 1);
      expect(records[0].length, 444);
      expect(r.pendingBytes, 0);
    });

    test('reassembles a record split across two BLE notifications', () {
      final r = RingRecordReassembler();
      // 300B chunk + 144B chunk = 444B = one record
      r.append(List.filled(300, 0x11));
      expect(r.drainRecords(), isEmpty);
      r.append(List.filled(144, 0x22));
      final records = r.drainRecords();
      expect(records.length, 1);
      expect(records[0].length, 444);
      // First 300 bytes are 0x11, next 144 are 0x22
      expect(records[0][0], 0x11);
      expect(records[0][299], 0x11);
      expect(records[0][300], 0x22);
      expect(records[0][443], 0x22);
    });

    test('emits multiple records and buffers leftover bytes', () {
      final r = RingRecordReassembler();
      // 1000 bytes = 2 records of 444 + 112 leftover
      r.append(List.filled(1000, 0x55));
      final records = r.drainRecords();
      expect(records.length, 2);
      expect(records[0].length, 444);
      expect(records[1].length, 444);
      expect(r.pendingBytes, 112);
    });

    test('preserves byte order across many small chunks', () {
      final r = RingRecordReassembler();
      // Build a unique byte pattern across 444 bytes and feed it 1 byte at a time.
      final expected = List<int>.generate(444, (i) => i & 0xFF);
      for (final b in expected) {
        r.append([b]);
      }
      final records = r.drainRecords();
      expect(records.length, 1);
      expect(records[0].toList(), expected);
    });

    test('handles a stream of two records with mid-record split', () {
      final r = RingRecordReassembler();
      // Build two records: rec1 = 0x01..0x01, rec2 = 0x02..0x02
      final rec1 = List.filled(444, 0x01);
      final rec2 = List.filled(444, 0x02);
      // Chunk 1: all of rec1 + first 100 bytes of rec2
      r.append([...rec1, ...rec2.sublist(0, 100)]);
      var records = r.drainRecords();
      expect(records.length, 1);
      expect(records[0][0], 0x01);
      expect(r.pendingBytes, 100);
      // Chunk 2: remaining 344 bytes of rec2
      r.append(rec2.sublist(100));
      records = r.drainRecords();
      expect(records.length, 1);
      expect(records[0].toList(), rec2);
      expect(r.pendingBytes, 0);
    });
  });

  group('end-to-end: NOTIFY_DATA reassembly + record decode', () {
    test('reconstructs a record split across two NOTIFY_DATA chunks and decodes audio', () {
      // Construct one record: ts=0xDEADBEEF, then two 80B opus-like frames.
      final ts = 0xDEADBEEF;
      final f1 = List<int>.generate(80, (i) => 0xA0 + (i & 0x0F));
      final f2 = List<int>.generate(80, (i) => 0x50 + (i & 0x0F));
      final audio = <int>[80, ...f1, 80, ...f2];
      audio.addAll(List.filled(440 - audio.length, 0));
      final record = <int>[
        (ts >> 24) & 0xFF,
        (ts >> 16) & 0xFF,
        (ts >> 8) & 0xFF,
        ts & 0xFF,
        ...audio,
      ];
      expect(record.length, 444);

      // Split across two BLE chunks at an arbitrary boundary.
      final reassembler = RingRecordReassembler();
      reassembler.append(record.sublist(0, 137));
      expect(reassembler.drainRecords(), isEmpty);
      reassembler.append(record.sublist(137));

      final records = reassembler.drainRecords();
      expect(records.length, 1);
      expect(RingProtocol.readRecordTimestamp(records[0]), ts);

      final audioPayload = records[0].sublist(RingProtocol.timestampBytes);
      final frames = RingProtocol.parseAudioPayload(audioPayload);
      expect(frames.length, 2);
      expect(frames[0], f1);
      expect(frames[1], f2);
    });
  });
}
