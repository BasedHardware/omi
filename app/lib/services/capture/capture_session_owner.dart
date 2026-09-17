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

class _InFlightConnect {
  _InFlightConnect({required this.generation, required this.configuration, required this.epoch, required this.future});
  final int generation;
  final String configuration;
  final int epoch;
  final Future<dynamic> future;
}

class _PublishedConnect {
  _PublishedConnect(this.value, this.close);
  final dynamic value;
  final Future<void> Function(dynamic value) close;
}

/// Extracted ownership boundary; implementation belongs to App core/C1.
/// No constructor below resolves a singleton or starts work.
class CaptureSessionOwner implements CaptureRecoveryRequests {
  CaptureSessionOwner({
    required RecordingTransferCoordinator coordinator,
    required Future<void> Function() startForeground,
    required Future<void> Function() stopForeground,
  })  : _coordinator = coordinator,
        _startForeground = startForeground,
        _stopForeground = stopForeground;

  // FGS stays on a later cut; the constructor contract is stored so that cut
  // does not change the explicit composition shape.
  final RecordingTransferCoordinator _coordinator;
  // ignore: unused_field
  final Future<void> Function() _startForeground;
  // ignore: unused_field
  final Future<void> Function() _stopForeground;

  int _generation = 0;
  String _identity = '';
  int _connectEpoch = 0;
  bool _closed = false;
  _InFlightConnect? _inFlight;
  _PublishedConnect? _published;
  Future<void>? _closeFinished;

  CaptureSessionToken get token => CaptureSessionToken(_generation, _identity);

  bool isCurrent(CaptureSessionToken token) =>
      !_closed && token.generation == _generation && token.identity == _identity;

  void replaceSession(String identity) {
    _identity = identity;
    _generation++;
    _connectEpoch++;
  }

  /// A generation is captured BEFORE prepare; only a current completion commits.
  /// commit is synchronous: async effects need their own check at each await.
  Future<void> prepareCurrent<T>(Future<T> Function() prepare, void Function(T) commit) async {
    final captured = token;
    final value = await prepare();
    if (!isCurrent(captured)) return;
    commit(value);
  }

  /// Same generation/configuration joins one attempt. A superseded result is
  /// disposed before completion and is never published to the active session.
  Future<T?> connect<T>({
    required String configuration,
    required Future<T> Function() open,
    required Future<void> Function(T) close,
  }) {
    if (_closed) return Future<T?>.value(null);
    final inFlight = _inFlight;
    if (inFlight != null && inFlight.generation == _generation && inFlight.configuration == configuration) {
      return inFlight.future as Future<T?>;
    }

    final generation = _generation;
    final epoch = ++_connectEpoch;
    final completer = Completer<T?>();
    _inFlight = _InFlightConnect(
      generation: generation,
      configuration: configuration,
      epoch: epoch,
      future: completer.future,
    );

    () async {
      try {
        final result = await open();
        final superseded = _closed || generation != _generation || epoch != _connectEpoch;
        if (superseded) {
          await close(result);
          if (!completer.isCompleted) completer.complete(null);
          return;
        }
        final previous = _published;
        _published = _PublishedConnect(result, (dynamic value) => close(value as T));
        if (previous != null) {
          await previous.close(previous.value);
        }
        if (!completer.isCompleted) completer.complete(result);
      } catch (error, stack) {
        if (!completer.isCompleted) completer.completeError(error, stack);
      } finally {
        if (_inFlight?.epoch == epoch) _inFlight = null;
      }
    }();

    return completer.future;
  }

  Future<void> setForegroundRequired(bool required) => throw UnimplementedError('C1 ordered FGS intent');
  bool get foregroundRunning => throw UnimplementedError('C1 settled FGS state');

  @override
  Future<void> requestRecovery(WakeTrigger trigger, {int? inventoryRevision}) =>
      throw UnimplementedError('C1 coalesced recovery request');

  /// Generation-guarded coordinator wake. Distinct from [requestRecovery]
  /// coalescing, which is a later C1 cut.
  Future<void> wakeIfCurrent(CaptureSessionToken token, WakeTrigger trigger) async {
    if (!isCurrent(token)) return;
    await _coordinator.wake(trigger);
  }

  /// Invalidates synchronously, then drains owned teardown. Idempotent.
  Future<void> close() {
    if (_closed) return _closeFinished ?? Future<void>.value();
    _closed = true;
    _generation++;
    _connectEpoch++;
    return _closeFinished ??= _drainClose();
  }

  Future<void> _drainClose() async {
    final published = _published;
    _published = null;
    if (published != null) {
      await published.close(published.value);
    }
  }
}
