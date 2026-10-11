import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/devices/connectors/limitless_clock_drift.dart';

List<int> varint(int value) {
  final out = <int>[];
  var v = value;
  while (v > 0x7f) {
    out.add((v & 0x7f) | 0x80);
    v >>= 7;
  }
  out.add(v & 0x7f);
  return out;
}

List<int> intField(int fieldNum, int value) => [...varint((fieldNum << 3) | 0), ...varint(value)];

List<int> bytesField(int fieldNum, List<int> data) => [...varint((fieldNum << 3) | 2), ...varint(data.length), ...data];

List<int> bleWrapper(int index, int seq, int numFrags, List<int> payload) => [
      ...intField(1, index),
      ...intField(2, seq),
      ...intField(3, numFrags),
      ...bytesField(4, payload),
    ];

void main() {
  group('Type-8 pendant clock parse', () {
    test('extracts epoch from f8→f6 varint', () {
      const epoch = 1750000005000;
      final payload = bytesField(8, intField(6, epoch));
      expect(LimitlessClockDrift.extractType8PendantEpochMs(payload), epoch);
    });

    test('extracts epoch from f8→f6→f1 nested', () {
      const epoch = 1750000005000;
      final payload = bytesField(8, bytesField(6, intField(1, epoch)));
      expect(LimitlessClockDrift.extractType8PendantEpochMs(payload), epoch);
    });

    test('extracts epoch from BLE-wrapped f4→f8→f6', () {
      const epoch = 1750000005000;
      final packet = bleWrapper(1, 0, 1, bytesField(8, intField(6, epoch)));
      expect(LimitlessClockDrift.extractType8PendantEpochMs(packet), epoch);
    });

    test('extracts epoch from f1=8 message type with sibling f6', () {
      const epoch = 1750000005000;
      final payload = [...intField(1, 8), ...intField(6, epoch)];
      expect(LimitlessClockDrift.extractType8PendantEpochMs(payload), epoch);
    });

    test('returns null when field 8 is absent', () {
      final payload = bytesField(2, intField(1, 42));
      expect(LimitlessClockDrift.extractType8PendantEpochMs(payload), isNull);
    });

    test('returns null for mode-only Type-8 with no clock field', () {
      // msg8 download/stream flags: f1=batch, f2=realtime — no f6 epoch.
      final payload = bytesField(8, [...intField(1, 1), ...intField(2, 0)]);
      expect(LimitlessClockDrift.extractType8PendantEpochMs(payload), isNull);
    });

    test('returns null for unterminated varint in Type-8 payload', () {
      final payload = <int>[
        (8 << 3) | 2, // field 8, wire type 2
        0x80, 0x80, 0x80, // unterminated length varint
      ];
      expect(LimitlessClockDrift.extractType8PendantEpochMs(payload), isNull);
    });

    test('returns null for epoch below the 2020 sanity floor', () {
      final payload = bytesField(8, intField(6, 1));
      expect(LimitlessClockDrift.extractType8PendantEpochMs(payload), isNull);
    });
  });

  group('clock-drift measurement', () {
    test('returns pendant minus phone', () {
      expect(
        LimitlessClockDrift.measureClockDriftOffsetMs(pendantEpochMs: 1750000180000, phoneEpochMs: 1750000000000),
        180000,
      );
    });

    test('returns null for implausible multi-week offset', () {
      expect(
        LimitlessClockDrift.measureClockDriftOffsetMs(
          pendantEpochMs: 1750000000000 + LimitlessClockDrift.maxAbsDriftMs + 1,
          phoneEpochMs: 1750000000000,
        ),
        isNull,
      );
    });

    test('returns null for pendant epoch below the sanity floor', () {
      expect(LimitlessClockDrift.measureClockDriftOffsetMs(pendantEpochMs: 1, phoneEpochMs: 1750000000000), isNull);
    });
  });

  group('flash-page timestamp correction (#5734)', () {
    test('subtracts drift when a pendant page timestamp is present', () {
      const driftOffsetMs = 5 * 60 * 1000;
      const rawTimestampMs = 1750000000000;
      const phoneNowMs = 1750000600000;
      expect(
        LimitlessClockDrift.correctedFlashPageTimestampMs(
          pageTimestampMs: rawTimestampMs,
          clockDriftOffsetMs: driftOffsetMs,
          phoneNowMs: phoneNowMs,
        ),
        rawTimestampMs - driftOffsetMs,
      );
    });

    test('does not double-correct DateTime.now fallback when page timestamp is missing', () {
      const driftOffsetMs = 5 * 60 * 1000;
      const phoneNowMs = 1750000600000;
      expect(
        LimitlessClockDrift.correctedFlashPageTimestampMs(
          pageTimestampMs: null,
          clockDriftOffsetMs: driftOffsetMs,
          phoneNowMs: phoneNowMs,
        ),
        phoneNowMs,
      );
    });

    test('does not apply drift to a zero/unset page timestamp', () {
      const phoneNowMs = 1750000600000;
      expect(
        LimitlessClockDrift.correctedFlashPageTimestampMs(
          pageTimestampMs: 0,
          clockDriftOffsetMs: 5 * 60 * 1000,
          phoneNowMs: phoneNowMs,
        ),
        phoneNowMs,
      );
    });

    test('treats null drift as zero correction', () {
      const rawTimestampMs = 1750000000000;
      expect(
        LimitlessClockDrift.correctedFlashPageTimestampMs(
          pageTimestampMs: rawTimestampMs,
          clockDriftOffsetMs: null,
          phoneNowMs: 0,
        ),
        rawTimestampMs,
      );
    });
  });
}
