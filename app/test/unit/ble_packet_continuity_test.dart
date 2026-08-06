import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/devices/ble_packet_continuity.dart';

List<int> _packet(int id) => [id & 0xFF, (id >> 8) & 0xFF, 0, 0xAA];

void main() {
  group('BlePacketContinuityTracker', () {
    test('accepts contiguous IDs across the uint16 wrap', () {
      final tracker = BlePacketContinuityTracker();

      expect(tracker.observe(_packet(0xFFFE)).disposition, BlePacketDisposition.first);
      expect(tracker.observe(_packet(0xFFFF)).disposition, BlePacketDisposition.contiguous);
      expect(tracker.observe(_packet(0)).disposition, BlePacketDisposition.contiguous);
    });

    test('reports the exact number of missing packets', () {
      final tracker = BlePacketContinuityTracker();
      tracker.observe(_packet(100));

      final observation = tracker.observe(_packet(104));

      expect(observation.disposition, BlePacketDisposition.gap);
      expect(observation.missingPackets, 3);
      expect(observation.shouldForward, isTrue);
    });

    test('suppresses an exact adjacent duplicate without moving the cursor', () {
      final tracker = BlePacketContinuityTracker();
      tracker.observe(_packet(200));

      final duplicate = tracker.observe(_packet(200));
      final next = tracker.observe(_packet(201));

      expect(duplicate.disposition, BlePacketDisposition.duplicate);
      expect(duplicate.shouldForward, isFalse);
      expect(next.disposition, BlePacketDisposition.contiguous);
    });

    test('forwards a reused ID when the index or payload differs', () {
      final tracker = BlePacketContinuityTracker();
      tracker.observe(_packet(200));

      final reused = tracker.observe([200, 0, 1, 0xBB]);

      expect(reused.disposition, BlePacketDisposition.reset);
      expect(reused.shouldForward, isTrue);
    });

    test('forwards a backward reset instead of creating a long outage', () {
      final tracker = BlePacketContinuityTracker();
      tracker.observe(_packet(5000));

      final reset = tracker.observe(_packet(1));

      expect(reset.disposition, BlePacketDisposition.reset);
      expect(reset.shouldForward, isTrue);
      expect(tracker.observe(_packet(2)).disposition, BlePacketDisposition.contiguous);
    });

    test('uses modular half-range classification for ambiguous high-ID wrap gaps', () {
      final tracker = BlePacketContinuityTracker();
      tracker.observe(_packet(50000));

      final ambiguous = tracker.observe(_packet(1));

      expect(ambiguous.disposition, BlePacketDisposition.gap);
      expect(ambiguous.missingPackets, 15536);
      expect(ambiguous.shouldForward, isTrue);
    });

    test('rejects malformed packets without changing continuity', () {
      final tracker = BlePacketContinuityTracker();
      tracker.observe(_packet(10));

      expect(tracker.observe([1, 2]).disposition, BlePacketDisposition.malformed);
      expect(tracker.observe(_packet(11)).disposition, BlePacketDisposition.contiguous);
    });
  });

  group('BlePacketAnomalyLogLimiter', () {
    test('emits immediately then coalesces notification-rate anomalies', () {
      final limiter = BlePacketAnomalyLogLimiter(interval: const Duration(seconds: 10));
      final start = DateTime.utc(2026, 1, 1);

      expect(limiter.record(start), 1);
      expect(limiter.record(start.add(const Duration(seconds: 1))), isNull);
      expect(limiter.record(start.add(const Duration(seconds: 9))), isNull);
      expect(limiter.record(start.add(const Duration(seconds: 10))), 3);
    });
  });
}
