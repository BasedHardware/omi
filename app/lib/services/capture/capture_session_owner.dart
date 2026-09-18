import 'dart:async';

import 'package:omi/services/wals/recording_transfer_coordinator.dart';

/// C1 request surface. Callers never receive the coordinator or its drain.
abstract interface class CaptureRecoveryRequests {
  Future<void> requestRecovery(WakeTrigger trigger, {int? inventoryRevision});
}

class CaptureSessionToken {
  const CaptureSessionToken(this.generation, this.identity);
  final int generation;
  final String identity;
}

/// Extracted ownership boundary; implementation belongs to App core/C1.
/// No constructor below resolves a singleton or starts work.
class CaptureSessionOwner implements CaptureRecoveryRequests {
  CaptureSessionOwner({
    required RecordingTransferCoordinator coordinator,
    required Future<void> Function() startForeground,
    required Future<void> Function() stopForeground,
  });

  CaptureSessionToken get token => throw UnimplementedError('C1 session generation');
  bool isCurrent(CaptureSessionToken token) => throw UnimplementedError('C1 generation check');
  void replaceSession(String identity) => throw UnimplementedError('C1 invalidate before awaits');

  /// A generation is captured BEFORE prepare; only a current completion commits.
  /// commit is synchronous: async effects need their own check at each await.
  Future<void> prepareCurrent<T>(Future<T> Function() prepare, void Function(T) commit) =>
      throw UnimplementedError('C1 generation-guarded completion');

  /// Same generation/configuration joins one attempt. A superseded result is
  /// disposed before completion and is never published to the active session.
  Future<T?> connect<T>({
    required String configuration,
    required Future<T> Function() open,
    required Future<void> Function(T) close,
  }) => throw UnimplementedError('C1 single socket attempt');

  Future<void> setForegroundRequired(bool required) => throw UnimplementedError('C1 ordered FGS intent');
  bool get foregroundRunning => throw UnimplementedError('C1 settled FGS state');

  @override
  Future<void> requestRecovery(WakeTrigger trigger, {int? inventoryRevision}) =>
      throw UnimplementedError('C1 coalesced recovery request');

  /// Invalidates synchronously, then drains owned teardown. Idempotent.
  Future<void> close() => throw UnimplementedError('C1 owner teardown');
}
