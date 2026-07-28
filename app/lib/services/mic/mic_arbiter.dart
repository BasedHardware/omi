import 'dart:typed_data';

import 'package:omi/services/services.dart';

/// Single-owner token shared by every microphone stack (flutter_sound and the
/// native iOS recorder), so two stacks can never hold the mic — and fight over
/// the AVAudioSession — at the same time.
class MicArbiter {
  String? _owner;

  String? get owner => _owner;

  bool tryAcquire(String owner) {
    if (_owner != null && _owner != owner) return false;
    _owner = owner;
    return true;
  }

  void release(String owner) {
    if (_owner == owner) _owner = null;
  }
}

/// Decorator gating an [IMicRecorderService] behind a shared [MicArbiter].
/// Contention throws a [StateError], mirroring [MicRecorderService]'s existing
/// "Recorder is recording" throw — but consistently across both stacks.
class ArbitratedMic implements IMicRecorderService {
  final IMicRecorderService _inner;
  final MicArbiter _arbiter;
  final String _owner;

  ArbitratedMic({required IMicRecorderService inner, required MicArbiter arbiter, required String owner})
      : _inner = inner,
        _arbiter = arbiter,
        _owner = owner;

  @override
  Future<void> start({
    required Function(Uint8List bytes) onByteReceived,
    Function()? onRecording,
    Function()? onStop,
    Function()? onInitializing,
    Function()? onStalled,
    Function(bool began)? onInterruption,
  }) async {
    if (!_arbiter.tryAcquire(_owner)) {
      throw StateError('Microphone is busy (held by ${_arbiter.owner})');
    }
    try {
      await _inner.start(
        onByteReceived: onByteReceived,
        onRecording: onRecording,
        onStop: () {
          // Release on natural stops too (e.g. recorder self-retired), so a
          // dead session can never deadlock the other mic consumer.
          _arbiter.release(_owner);
          onStop?.call();
        },
        onInitializing: onInitializing,
        onStalled: onStalled,
        onInterruption: onInterruption,
      );
    } catch (e) {
      _arbiter.release(_owner);
      rethrow;
    }
  }

  @override
  Future<void> startBatch({
    Function()? onStop,
    Function(bool began)? onInterruption,
    Function()? onBatchStalled,
    Function(String code, String message)? onError,
  }) async {
    if (!_arbiter.tryAcquire(_owner)) {
      throw StateError('Microphone is busy (held by ${_arbiter.owner})');
    }
    try {
      await _inner.startBatch(
        onStop: () {
          _arbiter.release(_owner);
          onStop?.call();
        },
        onInterruption: onInterruption,
        onBatchStalled: onBatchStalled,
        onError: onError,
      );
    } catch (e) {
      _arbiter.release(_owner);
      rethrow;
    }
  }

  @override
  void stop() {
    _inner.stop();
    _arbiter.release(_owner);
  }
}
