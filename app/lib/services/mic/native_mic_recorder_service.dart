import 'dart:async';
import 'dart:typed_data';

import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/logger.dart';

/// iOS-only [IMicRecorderService] backed by the native PhoneMic module — an
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

  final PhoneMicHostApi _hostApi;
  final DateTime Function() _now;

  Function(Uint8List bytes)? _onByteReceived;
  Function()? _onRecording;
  Function()? _onStop;
  Function()? _onInitializing;
  Function()? _onStalled;
  Function(bool began)? _onInterruption;

  bool _sessionActive = false;
  bool _interrupted = false;
  DateTime? _lastByteAt;
  Timer? _stallTimer;
  bool _stallReported = false;

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
    _sessionActive = true;
    try {
      // Throws a PlatformException (permission_denied, session_config_failed,
      // format_invalid, converter_init_failed, engine_start_failed) instead of
      // recording silence.
      await _hostApi.start();
    } catch (e) {
      _sessionActive = false;
      _cancelStallWatchdog();
      _clearCallbacks();
      rethrow;
    }
  }

  @override
  void stop() {
    if (!_sessionActive) return;
    _sessionActive = false;
    _interrupted = false;
    _cancelStallWatchdog();
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
    switch (state) {
      case PhoneMicCaptureState.starting:
        _onInitializing?.call();
        break;
      case PhoneMicCaptureState.running:
        if (_interrupted) {
          _interrupted = false;
          _onInterruption?.call(false);
        }
        // Armed here rather than in start(): the permission prompt can hold
        // start() open far longer than the stall threshold.
        _startStallWatchdog();
        _onRecording?.call();
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
        _cancelStallWatchdog();
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

  void _clearCallbacks() {
    _onByteReceived = null;
    _onRecording = null;
    _onStop = null;
    _onInitializing = null;
    _onStalled = null;
    _onInterruption = null;
  }
}
