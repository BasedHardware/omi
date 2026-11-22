/// Default-on, matching the app's compile-time custody recovery kill switches.
const batchRingProofEnabled = !bool.fromEnvironment('OMI_BATCH_RING_PROOF_OFF', defaultValue: false);

/// Ordinals are local to this exact live session, never just to a ring or an
/// integer connection epoch (which can repeat after process restart).
class BatchLiveContext {
  const BatchLiveContext(this.deviceId, this.ringId, this.epoch, this.sessionId);
  final String deviceId;
  final int ringId;
  final int epoch;
  final String sessionId;

  @override
  bool operator ==(Object other) =>
      other is BatchLiveContext &&
      deviceId == other.deviceId &&
      ringId == other.ringId &&
      epoch == other.epoch &&
      sessionId == other.sessionId;

  @override
  int get hashCode => Object.hash(deviceId, ringId, epoch, sessionId);
}
