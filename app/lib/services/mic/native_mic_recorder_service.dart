import 'dart:async';
import 'dart:typed_data';

import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/logger.dart';

/// iOS/Android [IMicRecorderService] backed by the native PhoneMic module — an
/// AVAudioEngine capture layer with self-healing interruption and route-change
/// recovery.
///
/// Interruptions are NOT restarted from Dart: the native controller resumes
/// itself and this service only mirrors state into the existing callbacks
/// (`onInterruption(true/false)` for UI state, `onRecording` on resume). The
/// 3s stall watchdog — same constants as [MicRecorderService] — stays as the
/// outer safety net: CaptureController escalates a stall to stop()+start().
class NativeMicRecorderService implements IMicRecorderService, PhoneMicFlutterApi {
  static const Duration _stallThreshold = Duration(seconds: 3);
  static const Duration _stallCheckInterval = Duration(seconds: 1);
  // Batch has no frames; liveness is the arrival of onBatchProgress (1Hz), which
  // keeps ticking through mutes/interruptions. A longer window than the stream
  // stall threshold tolerates the coarser cadence.
  static const Duration _batchStallThreshold = Duration(seconds: 10);

  final PhoneMicHostApi _hostApi;
  final DateTime Function() _now;

  Function(Uint8List bytes)? _onByteReceived;
  Function()? _onRecording;
  Function()? _onStop;
  Function()? _onInitializing;
  Function()? _onStalled;
  Function(bool began)? _onInterruption;
  Function()? _onBatchStalled;
  Function(String code, String message)? _onError;

  bool _sessionActive = false;
  bool _sessionStarted = false;
  bool _batchMode = false;
  bool _interrupted = false;
  DateTime? _lastByteAt;
  Timer? _stallTimer;
  bool _stallReported = false;
  DateTime? _lastBatchProgressAt;
  Timer? _batchStallTimer;
  bool _batchStallReported = false;

  NativeMicRecorderService({
    PhoneMicHostApi? hostApi,
    bool registerFlutterApi = true,
    DateTime Function() now = DateTime.now,
  })  : _hostApi = hostApi ?? PhoneMicHostApi(),
        _now = now {
    if (registerFlutterApi) {
      PhoneMicFlutterApi.setUp(this);
    }
  }

  @override
  Future<void> start({
    required Function(Uint8List bytes) onByteReceived,
    Function()? onRecording,
    Function()? onStop,
    Function()? onInitializing,
    Function()? onStalled,
    Function(bool began)? onInterruption,
  }) async {
    _onByteReceived = onByteReceived;
    _onRecording = onRecording;
    _onStop = onStop;
    _onInitializing = onInitializing;
    _onStalled = onStalled;
    _onInterruption = onInterruption;
    _interrupted = false;
    _batchMode = false;
    _sessionActive = true;
    _sessionStarted = false;
    try {
      // Throws a PlatformException (permission_denied, session_config_failed,
      // format_invalid, converter_init_failed, engine_start_failed) instead of
      // recording silence.
      await _hostApi.start(PhoneMicCaptureMode.stream);
    } catch (e) {
      _sessionActive = false;
      _cancelStallWatchdog();
      _clearCallbacks();
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
    _onStop = onStop;
    _onInterruption = onInterruption;
    _onBatchStalled = onBatchStalled;
    _onError = onError;
    _interrupted = false;
    _batchMode = true;
    _sessionActive = true;
    _sessionStarted = false;
    try {
      // Batch adds opus_init_failed / batch_dir_unavailable to the stream error
      // codes; the native writer stores .bin files instead of streaming frames.
      await _hostApi.start(PhoneMicCaptureMode.batch);
    } catch (e) {
      _sessionActive = false;
      _batchMode = false;
      _cancelBatchWatchdog();
      _clearCallbacks();
      rethrow;
    }
  }

  @override
  void stop() {
    if (!_sessionActive) return;
    _sessionActive = false;
    _interrupted = false;
    _batchMode = false;
    _cancelStallWatchdog();
    _cancelBatchWatchdog();
    () async {
      try {
        await _hostApi.stop();
      } catch (e) {
        Logger.error('[NativeMic] native stop failed: $e');
      }
    }();
    final onStop = _onStop;
    _clearCallbacks();
    onStop?.call();
  }

  // PhoneMicFlutterApi

  @override
  void onAudioFrame(Uint8List pcm16leMono16k) {
    _lastByteAt = _now();
    _stallReported = false;
    _onByteReceived?.call(pcm16leMono16k);
  }

  @override
  void onStateChanged(PhoneMicCaptureState state) {
    if (!_sessionActive) return;
    // Stale-session gate. The native controller emits `starting` exactly once
    // per session, synchronously in handleStart, before any other event of that
    // session (failStart/finishStop `idle` always come after it), and channel
    // delivery is FIFO. So any event that arrives after start()/startBatch() has
    // armed a new session but before that session's own `starting` provably
    // belongs to a previous (dead) session — most dangerously a late `idle` that
    // would clobber the new session's callbacks. Drop them all uniformly.
    if (state == PhoneMicCaptureState.starting) {
      _sessionStarted = true;
    } else if (!_sessionStarted) {
      Logger.debug('[NativeMic] dropping stale $state from a previous session');
      return;
    }
    switch (state) {
      case PhoneMicCaptureState.starting:
        _onInitializing?.call();
        break;
      case PhoneMicCaptureState.running:
        if (_interrupted) {
          _interrupted = false;
          _onInterruption?.call(false);
        }
        if (_batchMode) {
          // Batch emits no frames, so the stream stall watchdog would misfire.
          // Arm the batch (progress-arrival) watchdog once, on the first running.
          if (_batchStallTimer == null) _startBatchWatchdog();
        } else {
          // Armed here rather than in start(): the permission prompt can hold
          // start() open far longer than the stall threshold.
          _startStallWatchdog();
          _onRecording?.call();
        }
        break;
      case PhoneMicCaptureState.interrupted:
        if (!_interrupted) {
          _interrupted = true;
          _onInterruption?.call(true);
        }
        break;
      case PhoneMicCaptureState.rebuilding:
        // Frames pause briefly during a route/config rebuild — fresh grace
        // period so the watchdog doesn't misread it as a stall.
        _lastByteAt = _now();
        break;
      case PhoneMicCaptureState.idle:
        // Native-side terminal stop without a Dart stop() call.
        _sessionActive = false;
        _interrupted = false;
        _batchMode = false;
        _cancelStallWatchdog();
        _cancelBatchWatchdog();
        final onStop = _onStop;
        _clearCallbacks();
        onStop?.call();
        break;
    }
  }

  @override
  void onCaptureError(String code, String message) {
    // Native self-heals; the stall watchdog is the escalation path.
    Logger.error('[NativeMic] capture error $code: $message');
    // In batch there is no socket/UI listening for frames, so surface the code
    // (e.g. batch_storage_full) to the session so CaptureController can react.
    if (_batchMode) _onError?.call(code, message);
  }

  @override
  void onBatchProgress(double capturedSeconds) {
    if (!_sessionActive || !_batchMode) return;
    // Arrival — not value — is the liveness signal: the value freezes during
    // mutes/interruptions while events keep coming.
    _lastBatchProgressAt = _now();
    _batchStallReported = false;
  }

  void _startStallWatchdog() {
    _cancelStallWatchdog();
    _lastByteAt = _now();
    _stallReported = false;
    _stallTimer = Timer.periodic(_stallCheckInterval, (_) {
      if (_stallReported || _lastByteAt == null || _interrupted || !_sessionActive) return;
      if (_now().difference(_lastByteAt!) >= _stallThreshold) {
        _stallReported = true;
        _onStalled?.call();
      }
    });
  }

  void _cancelStallWatchdog() {
    _stallTimer?.cancel();
    _stallTimer = null;
    _lastByteAt = null;
    _stallReported = false;
  }

  void _startBatchWatchdog() {
    _cancelBatchWatchdog();
    _lastBatchProgressAt = _now();
    _batchStallReported = false;
    _batchStallTimer = Timer.periodic(_stallCheckInterval, (_) {
      if (_batchStallReported || _lastBatchProgressAt == null || !_sessionActive) return;
      if (_now().difference(_lastBatchProgressAt!) >= _batchStallThreshold) {
        _batchStallReported = true;
        _onBatchStalled?.call();
      }
    });
  }

  void _cancelBatchWatchdog() {
    _batchStallTimer?.cancel();
    _batchStallTimer = null;
    _lastBatchProgressAt = null;
    _batchStallReported = false;
  }

  void _clearCallbacks() {
    _onByteReceived = null;
    _onRecording = null;
    _onStop = null;
    _onInitializing = null;
    _onStalled = null;
    _onInterruption = null;
    _onBatchStalled = null;
    _onError = null;
  }
}
