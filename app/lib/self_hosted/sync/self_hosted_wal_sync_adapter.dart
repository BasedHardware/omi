enum SelfHostedWalSyncResult { disabled, deferred }

abstract interface class SelfHostedWalSyncAdapter {
  bool get enabled;
  Future<SelfHostedWalSyncResult> schedule({required String walId});
}

/// Deliberately does not upload or acknowledge a WAL item.
///
/// It is a configuration and call-shape seam only. Connecting it to
/// `LocalWalSyncImpl` requires a confirmed Worker upload/ack contract.
class NoopSelfHostedWalSyncAdapter implements SelfHostedWalSyncAdapter {
  NoopSelfHostedWalSyncAdapter({bool? enabled}) : _enabled = enabled ?? _environmentEnabled;

  static bool get _environmentEnabled =>
      const bool.fromEnvironment('BRAINBASE_SELF_HOSTED_SYNC') &&
      const String.fromEnvironment('BRAINBASE_SELF_HOSTED_WORKER_URL').isNotEmpty &&
      const String.fromEnvironment('BRAINBASE_SELF_HOSTED_WORKER_TOKEN').isNotEmpty;

  final bool _enabled;

  @override
  bool get enabled => _enabled;

  @override
  Future<SelfHostedWalSyncResult> schedule({required String walId}) async {
    if (walId.isEmpty) throw ArgumentError.value(walId, 'walId', 'must not be empty');
    return enabled ? SelfHostedWalSyncResult.deferred : SelfHostedWalSyncResult.disabled;
  }
}
