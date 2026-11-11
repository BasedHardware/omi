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

  final RecordingTransferCoordinator _coordinator;
  final Future<void> Function() _startForeground;
  final Future<void> Function() _stopForeground;

  int _generation = 0;
  String _identity = '';
  int _connectEpoch = 0;
  bool _closed = false;
  bool _desiredForeground = false;
  bool _foregroundRunning = false;
  Future<void>? _foregroundOp;
  Future<void>? _recoveryJoin;
  WakeTrigger? _coalescedTrigger;
  int? _recoveryRevision;
  bool _recoveryWakeStarted = false;
  _InFlightConnect? _inFlight;
  _PublishedConnect? _published;
  Future<void>? _closeFinished;

  CaptureSessionToken get token => CaptureSessionToken(_generation, _identity);

  bool isCurrent(CaptureSessionToken token) =>
      !_closed && token.generation == _generation && token.identity == _identity;

  bool _connectIsCurrent(int generation, int epoch) => !_closed && generation == _generation && epoch == _connectEpoch;

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
        if (!_connectIsCurrent(generation, epoch)) {
          await close(result);
          if (!completer.isCompleted) completer.complete(null);
          return;
        }
        final previous = _published;
        _published = null;
        if (previous != null) {
          try {
            await previous.close(previous.value);
          } catch (error, stack) {
            await close(result);
            if (!completer.isCompleted) completer.completeError(error, stack);
            return;
          }
        }
        if (!_connectIsCurrent(generation, epoch)) {
          await close(result);
          if (!completer.isCompleted) completer.complete(null);
          return;
        }
        _published = _PublishedConnect(result, (dynamic value) => close(value as T));
        if (!completer.isCompleted) completer.complete(result);
      } catch (error, stack) {
        if (!completer.isCompleted) completer.completeError(error, stack);
      } finally {
        if (_inFlight?.epoch == epoch) _inFlight = null;
      }
    }();

    return completer.future;
  }

  /// Latest desired hold wins. A stop admitted while start is pending waits,
  /// then stops once; a failed start stays not-running and may retry.
  /// FGS publication is the settled running flag, not session identity: a
  /// replaceSession must not drop an admitted hold, but close() must.
  Future<void> setForegroundRequired(bool required) {
    if (_closed) {
      return required ? Future<void>.value() : _runForeground();
    }
    _desiredForeground = required;
    return _runForeground();
  }

  bool get foregroundRunning => _foregroundRunning;

  Future<void> _runForeground() {
    final existing = _foregroundOp;
    if (existing != null) return existing;
    final done = Completer<void>();
    _foregroundOp = done.future;
    () async {
      var failed = false;
      try {
        while (!_closed && _desiredForeground != _foregroundRunning) {
          if (_desiredForeground) {
            await _startForeground();
            if (_closed || !_desiredForeground) {
              await _stopForeground();
              _foregroundRunning = false;
              continue;
            }
            _foregroundRunning = true;
          } else {
            await _stopForeground();
            _foregroundRunning = false;
          }
        }
        if (_closed && _foregroundRunning) {
          await _stopForeground();
          _foregroundRunning = false;
        }
        if (!done.isCompleted) done.complete();
      } catch (error, stack) {
        failed = true;
        _foregroundRunning = false;
        if (!done.isCompleted) done.completeError(error, stack);
      } finally {
        _foregroundOp = null;
      }
      if (!failed && !_closed && _desiredForeground != _foregroundRunning) {
        await _runForeground();
      }
    }();
    return done.future;
  }

  /// Concurrent requests join the coordinator's in-flight pass; a later wake
  /// still runs. Pin the session at admit and refuse to attach completion to a
  /// later generation. An already-admitted drain is not undone.
  @override
  Future<void> requestRecovery(WakeTrigger trigger, {int? inventoryRevision}) {
    if (_closed) return Future<void>.value();
    final admitted = token;
    _coalescedTrigger = _preferTrigger(_coalescedTrigger, trigger);
    if (inventoryRevision != null && (_recoveryRevision == null || inventoryRevision > _recoveryRevision!)) {
      if (_recoveryWakeStarted) {
        unawaited(_coordinator.wake(trigger));
      }
      _recoveryRevision = inventoryRevision;
    } else if (_recoveryWakeStarted && trigger == WakeTrigger.userRetry) {
      unawaited(_coordinator.wake(trigger));
    }
    return _recoveryJoin ??= _runRecovery(admitted);
  }

  WakeTrigger _preferTrigger(WakeTrigger? existing, WakeTrigger incoming) {
    if (existing == WakeTrigger.userRetry || incoming != WakeTrigger.userRetry) {
      return existing ?? incoming;
    }
    return incoming;
  }

  Future<void> _runRecovery(CaptureSessionToken admitted) async {
    try {
      await Future<void>.delayed(Duration.zero);
      if (_closed || !isCurrent(admitted)) return;
      final trigger = _coalescedTrigger ?? WakeTrigger.startup;
      _recoveryWakeStarted = true;
      await _coordinator.wake(trigger);
    } finally {
      _recoveryJoin = null;
      _recoveryWakeStarted = false;
      _coalescedTrigger = null;
      _recoveryRevision = null;
    }
    if (!isCurrent(admitted)) return;
  }

  /// Generation-guarded coordinator wake. [requestRecovery] is the coalesced
  /// caller-facing admit; this helper skips a wake whose session already rolled.
  Future<void> wakeIfCurrent(CaptureSessionToken token, WakeTrigger trigger) async {
    if (!isCurrent(token)) return;
    await requestRecovery(trigger);
  }

  /// Invalidates synchronously, then drains owned teardown. Idempotent.
  Future<void> close() {
    if (_closed) return _closeFinished ?? Future<void>.value();
    _closed = true;
    _desiredForeground = false;
    _generation++;
    _connectEpoch++;
    return _closeFinished ??= _drainClose();
  }

  Future<void> _drainClose() async {
    try {
      await _runForeground();
    } catch (_) {
      // Close still drains sockets after a failed FGS stop.
    }
    final inFlight = _inFlight?.future;
    if (inFlight != null) {
      try {
        await inFlight;
      } catch (_) {
        // The connect caller already received the error.
      }
    }
    final published = _published;
    _published = null;
    if (published != null) {
      await published.close(published.value);
    }
  }
}
