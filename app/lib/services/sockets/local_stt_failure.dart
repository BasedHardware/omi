/// A local transcription failure requiring explicit setup or input repair.
/// Audio stays in the polling buffer and the existing WAL; no billed fallback.
class LocalSttFailure implements Exception {
  final String code;
  final bool canProbeRecovery;
  const LocalSttFailure(this.code, {this.canProbeRecovery = false});
  @override
  String toString() => 'Local transcription needs attention ($code)';
}

abstract interface class RecoverableLocalSttProvider {
  Future<bool> isReadyToRetry();
}
