import 'dart:async';

/// Roll back download receipts, ACK pruning and progress-based read ownership.
const ringDrainRecoveryEnabled = !bool.fromEnvironment('OMI_RING_DRAIN_RECOVERY_OFF');

/// The reader owns first-data / DATA-silence cancellation. Elapsed total time
/// cannot abandon an active transfer or its pending disk/index transactions.
Future<bool> waitForRingRead(Future<bool> completion) =>
    ringDrainRecoveryEnabled ? completion : completion.timeout(const Duration(minutes: 30));

/// Decode every complete packed frame before stamping a durable ring range.
/// Zero bytes are padding. A nonzero overrun cannot become an empty-record
/// proof or authorize reclaim of samples that were never written to the WAL.
List<List<int>> decodeCustodyRingAudio(List<int> payload) {
  final frames = <List<int>>[];
  var offset = 0;
  while (offset < payload.length) {
    final size = payload[offset++];
    if (size == 0) continue;
    final end = offset + size;
    if (end > payload.length) throw const FormatException('Incomplete packed ring frame');
    frames.add(payload.sublist(offset, end));
    offset = end;
  }
  return frames;
}
