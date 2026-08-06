enum BlePacketDisposition {
  first,
  contiguous,
  gap,
  duplicate,
  reset,
  malformed,
}

class BlePacketContinuityObservation {
  final BlePacketDisposition disposition;
  final int? packetId;
  final int missingPackets;

  const BlePacketContinuityObservation(this.disposition, {this.packetId, this.missingPackets = 0});

  bool get shouldForward =>
      disposition != BlePacketDisposition.duplicate && disposition != BlePacketDisposition.malformed;
}

/// Tracks Omi's 16-bit little-endian live-audio packet ID.
///
/// BLE notifications are ordered within a connection, so an exactly repeated
/// packet is a duplicate and a forward delta greater than one is a measurable
/// gap. The half-range modular rule distinguishes forward progress from reset:
/// some high-ID-to-low-ID jumps are inherently ambiguous and are reported as
/// gaps, but all anomalies except exact adjacent duplicates are forwarded.
class BlePacketContinuityTracker {
  int? _lastPacketId;
  List<int>? _lastPacket;

  BlePacketContinuityObservation observe(List<int> packet) {
    if (packet.length < 3) {
      return const BlePacketContinuityObservation(BlePacketDisposition.malformed);
    }

    final packetId = (packet[0] & 0xFF) | ((packet[1] & 0xFF) << 8);
    final previous = _lastPacketId;
    if (previous == null) {
      _lastPacketId = packetId;
      _lastPacket = List<int>.from(packet);
      return BlePacketContinuityObservation(BlePacketDisposition.first, packetId: packetId);
    }

    final delta = (packetId - previous) & 0xFFFF;
    if (delta == 0) {
      if (_packetsEqual(packet, _lastPacket!)) {
        return BlePacketContinuityObservation(BlePacketDisposition.duplicate, packetId: packetId);
      }

      // A repeated 16-bit ID with different index/payload can be a firmware
      // counter reset or another fragment from legacy firmware. Preserve it.
      _lastPacket = List<int>.from(packet);
      return BlePacketContinuityObservation(BlePacketDisposition.reset, packetId: packetId);
    }

    _lastPacketId = packetId;
    _lastPacket = List<int>.from(packet);
    if (delta == 1) {
      return BlePacketContinuityObservation(BlePacketDisposition.contiguous, packetId: packetId);
    }
    if (delta < 0x8000) {
      return BlePacketContinuityObservation(
        BlePacketDisposition.gap,
        packetId: packetId,
        missingPackets: delta - 1,
      );
    }
    return BlePacketContinuityObservation(BlePacketDisposition.reset, packetId: packetId);
  }

  bool _packetsEqual(List<int> left, List<int> right) {
    if (left.length != right.length) return false;
    for (var index = 0; index < left.length; index++) {
      if (left[index] != right[index]) return false;
    }
    return true;
  }
}

/// Coalesces continuity warnings so a damaged stream cannot enqueue a log write
/// for every BLE notification.
class BlePacketAnomalyLogLimiter {
  final Duration interval;
  DateTime? _lastEmission;
  int _pendingEvents = 0;

  BlePacketAnomalyLogLimiter({this.interval = const Duration(seconds: 10)});

  /// Returns the number of coalesced anomaly events when a warning should be
  /// emitted, or null when this event should be folded into the next warning.
  int? record(DateTime now) {
    _pendingEvents++;
    final lastEmission = _lastEmission;
    if (lastEmission != null && now.isBefore(lastEmission.add(interval))) {
      return null;
    }

    final events = _pendingEvents;
    _pendingEvents = 0;
    _lastEmission = now;
    return events;
  }
}
