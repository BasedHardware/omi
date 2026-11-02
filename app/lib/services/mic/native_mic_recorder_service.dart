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
///
/// Session identity: each start()/startBatch() mints a new monotonically
/// increasing [_sessionId] and passes it to native. Every FlutterApi event
/// carries the id of the session it belongs to, and every handler drops events
/// whose id is not the current one — so a stale terminal `idle` from a
/// just-stopped session cannot clobber a fresh session, and a de-synced restart
/// converges: native adopts the new id on a start onto a still-live session and
/// re-emits its current state under it, so `running` reaches the new session even
/// without a fresh `starting`. stop() always forwards to native (killing any
/// orphaned session) and only runs local teardown once.
class NativeMicRecorderService implements IMicRecorderService, PhoneMicFlutterApi {
  static const Duration _stallThreshold = Duration(seconds: 3);
  static const Duration _stallCheckInterval = Duration(seconds: 1);
  // Healthy-state cadence used only when [paceHealthyChecks] is set (iOS).
  // Capped by the stall deadline below, so a check is never scheduled later
  // than the moment the existing threshold would trip. Faults snap back to
  // [_stallCheckInterval].
  static const Duration _healthyCheckInterval = Duration(seconds: 5);
  // Batch has no frames; liveness is the arrival of onBatchProgress, which
  // keeps ticking through mutes/interruptions. A longer window than the stream
  // stall threshold tolerates the coarser cadence. The threshold itself is
  // unchanged: a missing beat is still a stall at 10s.
  static const Duration _batchStallThreshold = Duration(seconds: 10);

  final PhoneMicHostApi _hostApi;
  final Timer Function(Duration, void Function(Timer)) _periodic;
  final DateTime Function() _now;
  final bool _paceHealthyChecks;

  Function(Uint8List bytes)? _onByteReceived;
  Function()? _onRecording;
  Function()? _onStop;
  Function()? _onInitializing;
  Function()? _onStalled;
  Function(bool began)? _onInterruption;
  Function()? _onBatchStalled;
  Function(String code, String message)? _onError;

  bool _sessionActive = false;
  // Dart-minted session identity, bumped on every start()/startBatch(). Events
  // are dropped unless they carry this id (see the FlutterApi handlers below).
  int _sessionId = 0;
  bool _batchMode = false;
  bool _interrupted = false;
  DateTime? _lastByteAt;
  Timer? _stallTimer;
  bool _stallReported = false;
  bool _stallFastCadence = false;
  DateTime? _lastBatchProgressAt;
  Timer? _batchStallTimer;
  bool _batchStallReported = false;
  bool _batchFastCadence = false;

  NativeMicRecorderService({
    PhoneMicHostApi? hostApi,
    bool registerFlutterApi = true,
    DateTime Function() now = DateTime.now,
    Timer Function(Duration, void Function(Timer))? periodic,
    bool paceHealthyChecks = false,
  })  : _hostApi = hostApi ?? PhoneMicHostApi(),
        _now = now,
        _periodic = periodic ?? Timer.periodic,
        _paceHealthyChecks = paceHealthyChecks {
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
    final sessionId = ++_sessionId;
    try {
      // Throws a PlatformException (permission_denied, session_config_failed,
      // format_invalid, converter_init_failed, engine_start_failed) instead of
      // recording silence.
      await _hostApi.start(PhoneMicCaptureMode.stream, sessionId);
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
    final sessionId = ++_sessionId;
    try {
      // Batch adds opus_init_failed / batch_dir_unavailable to the stream error
      // codes; the native writer stores .bin files instead of streaming frames.
      await _hostApi.start(PhoneMicCaptureMode.batch, sessionId);
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
    // Always forward to native — even when Dart already thinks the session is
    // inactive. A de-synced Dart state must never leave a native session
    // capturing forever; native resolves harmlessly when it is already idle.
    () async {
      try {
        await _hostApi.stop();
      } catch (e) {
        Logger.error('[NativeMic] native stop failed: $e');
      }
    }();
    // Local teardown (and onStop) run only once, on the transition out of an
    // active session — so a second stop() (or a stop() after a native idle) does
    // not double-fire callbacks.
    if (!_sessionActive) return;
    _sessionActive = false;
    _interrupted = false;
    _batchMode = false;
    _cancelStallWatchdog();
    _cancelBatchWatchdog();
    final onStop = _onStop;
    _clearCallbacks();
    onStop?.call();
  }

  // PhoneMicFlutterApi

  @override
  void onAudioFrame(Uint8List pcm16leMono16k, int sessionId) {
    if (sessionId != _sessionId) {
      Logger.debug('[NativeMic] dropping frame from session $sessionId (current $_sessionId)');
      return;
    }
    _lastByteAt = _now();
    _stallReported = false;
    // Healthy frames must not reschedule the timer (that would be a wake per
    // buffer). Only leave the fast cadence once a fresh frame proves the
    // anomaly cleared.
    if (_paceHealthyChecks && !_interrupted && _stallFastCadence) {
      _armPacedStall(forceFast: false);
    }
    _onByteReceived?.call(pcm16leMono16k);
  }

  @override
  void onStateChanged(PhoneMicCaptureState state, int sessionId) {
    // Session-identity gate: events from a previous (dead) session — most
    // dangerously a late `idle` acknowledging its own stop — carry that
    // session's id and are dropped here so they cannot clobber the current one.
    if (sessionId != _sessionId) {
      Logger.debug('[NativeMic] dropping $state from session $sessionId (current $_sessionId)');
      return;
    }
    // An event for the current id after Dart-side stop (e.g. the terminal idle
    // acknowledging our own stop()) is still ignored.
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
        if (_batchMode) {
          // Batch emits no frames, so the stream stall watchdog would misfire.
          // Arm the batch (progress-arrival) watchdog once, on the first running.
          // A later running (resume) drops the interruption fast-cadence if the
          // heartbeat is fresh; a gap already in progress stays on the deadline.
          if (_batchStallTimer == null) {
            _startBatchWatchdog();
          } else if (_paceHealthyChecks) {
            _armPacedBatch(forceFast: false);
          }
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
        if (_paceHealthyChecks) {
          if (_batchMode && _lastBatchProgressAt != null) {
            _armPacedBatch(forceFast: true);
          } else if (_stallTimer != null) {
            _armPacedStall(forceFast: true);
          }
        }
        break;
      case PhoneMicCaptureState.rebuilding:
        // Frames pause briefly during a route/config rebuild — fresh grace
        // period so the watchdog doesn't misread it as a stall. Paced mode
        // also snaps to the 1s poll for the grace window.
        _lastByteAt = _now();
        if (_paceHealthyChecks) {
          if (_batchMode && _lastBatchProgressAt != null) {
            _armPacedBatch(forceFast: true);
          } else if (_stallTimer != null) {
            _armPacedStall(forceFast: true);
          }
        }
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
  void onCaptureError(String code, String message, int sessionId) {
    if (sessionId != _sessionId) {
      Logger.debug('[NativeMic] dropping error $code from session $sessionId (current $_sessionId)');
      return;
    }
    // Native self-heals; the stall watchdog is the escalation path.
    Logger.error('[NativeMic] capture error $code: $message');
    // In batch there is no socket/UI listening for frames, so surface the code
    // (e.g. batch_storage_full) to the session so CaptureController can react.
    if (_batchMode) _onError?.call(code, message);
  }

  @override
  void onBatchProgress(double capturedSeconds, int sessionId) {
    if (sessionId != _sessionId) {
      Logger.debug('[NativeMic] dropping batch progress from session $sessionId (current $_sessionId)');
      return;
    }
    if (!_sessionActive || !_batchMode) return;
    // Arrival — not value — is the liveness signal: the value freezes during
    // mutes/interruptions while events keep coming.
    _lastBatchProgressAt = _now();
    _batchStallReported = false;
    if (_paceHealthyChecks && !_interrupted && _batchFastCadence) {
      _armPacedBatch(forceFast: false);
    }
  }

  void _startStallWatchdog() {
    _cancelStallWatchdog();
    _lastByteAt = _now();
    _stallReported = false;
    if (!_paceHealthyChecks) {
      _stallTimer = _periodic(_stallCheckInterval, (_) {
        if (_stallReported || _lastByteAt == null || _interrupted || !_sessionActive) return;
        if (_now().difference(_lastByteAt!) >= _stallThreshold) {
          _stallReported = true;
          _onStalled?.call();
        }
      });
      return;
    }
    _armPacedStall(forceFast: false);
  }

  /// Next wake while paced. Never later than the stall deadline, and never
  /// later than the active cadence. [fast] is the 1s fault poll.
  Duration _pacedDelay({required Duration age, required Duration threshold, required bool fast}) {
    final interval = fast ? _stallCheckInterval : _healthyCheckInterval;
    final remaining = threshold - age;
    if (remaining <= Duration.zero) return Duration.zero;
    if (interval < remaining) return interval;
    return remaining;
  }

  void _armPacedStall({required bool forceFast}) {
    _stallTimer?.cancel();
    _stallTimer = null;
    if (!_sessionActive || _lastByteAt == null) return;
    // Interrupted stream silence is expected. Keep the fast poll so resume is
    // watched immediately, but do not declare a stall from this path.
    if (_interrupted) {
      _stallFastCadence = true;
      _stallTimer = Timer(_stallCheckInterval, _onPacedStallTick);
      return;
    }
    final age = _now().difference(_lastByteAt!);
    if (age >= _stallThreshold) {
      _stallFastCadence = true;
      _stallTimer = Timer(Duration.zero, () {
        if (_stallReported || _interrupted || !_sessionActive || _lastByteAt == null) return;
        if (_now().difference(_lastByteAt!) >= _stallThreshold) {
          _stallReported = true;
          _onStalled?.call();
        }
      });
      return;
    }
    final fast = forceFast || age >= _healthyCheckInterval;
    _stallFastCadence = fast;
    _stallTimer = Timer(_pacedDelay(age: age, threshold: _stallThreshold, fast: fast), _onPacedStallTick);
  }

  void _onPacedStallTick() {
    _stallTimer = null;
    if (!_sessionActive || _lastByteAt == null) return;
    if (_interrupted) {
      _armPacedStall(forceFast: true);
      return;
    }
    if (_stallReported) return;
    final age = _now().difference(_lastByteAt!);
    if (age >= _stallThreshold) {
      _stallReported = true;
      _onStalled?.call();
      return;
    }
    _armPacedStall(forceFast: age >= _healthyCheckInterval);
  }

  void _cancelStallWatchdog() {
    _stallTimer?.cancel();
    _stallTimer = null;
    _lastByteAt = null;
    _stallReported = false;
    _stallFastCadence = false;
  }

  void _startBatchWatchdog() {
    _cancelBatchWatchdog();
    _lastBatchProgressAt = _now();
    _batchStallReported = false;
    if (!_paceHealthyChecks) {
      _batchStallTimer = _periodic(_stallCheckInterval, (_) {
        if (_batchStallReported || _lastBatchProgressAt == null || !_sessionActive) return;
        if (_now().difference(_lastBatchProgressAt!) >= _batchStallThreshold) {
          _batchStallReported = true;
          _onBatchStalled?.call();
        }
      });
      return;
    }
    _armPacedBatch(forceFast: false);
  }

  void _armPacedBatch({required bool forceFast}) {
    _batchStallTimer?.cancel();
    _batchStallTimer = null;
    if (!_sessionActive || _lastBatchProgressAt == null) return;
    final age = _now().difference(_lastBatchProgressAt!);
    if (age >= _batchStallThreshold) {
      _batchFastCadence = true;
      _batchStallTimer = Timer(Duration.zero, () {
        if (_batchStallReported || !_sessionActive || _lastBatchProgressAt == null) return;
        if (_now().difference(_lastBatchProgressAt!) >= _batchStallThreshold) {
          _batchStallReported = true;
          _onBatchStalled?.call();
        }
      });
      return;
    }
    final fast = forceFast || _interrupted || age >= _healthyCheckInterval;
    _batchFastCadence = fast;
    _batchStallTimer = Timer(_pacedDelay(age: age, threshold: _batchStallThreshold, fast: fast), _onPacedBatchTick);
  }

  void _onPacedBatchTick() {
    _batchStallTimer = null;
    if (!_sessionActive || _lastBatchProgressAt == null || _batchStallReported) return;
    final age = _now().difference(_lastBatchProgressAt!);
    if (age >= _batchStallThreshold) {
      _batchStallReported = true;
      _onBatchStalled?.call();
      return;
    }
    _armPacedBatch(forceFast: _interrupted || age >= _healthyCheckInterval);
  }

  void _cancelBatchWatchdog() {
    _batchStallTimer?.cancel();
    _batchStallTimer = null;
    _lastBatchProgressAt = null;
    _batchStallReported = false;
    _batchFastCadence = false;
  }

  /// Soft-rearm liveness after the app returns to foreground (#4706).
  ///
  /// Wall-clock silence from timer suspension / screen lock must not force an
  /// immediate Dart stop→start (that races the native `appBecameActive` rebuild
  /// and also false-positives a healthy session). Reset the stall clock so the
  /// periodic watchdog owns escalation only if frames still don't arrive.
  @override
  void probeStallAfterForeground() {
    if (!_sessionActive || _interrupted) return;
    if (_batchMode) {
      _lastBatchProgressAt = _now();
      _batchStallReported = false;
      // Foreground is an anomaly edge: watch the next window at 1s, and let
      // the next progress beat return to the healthy cadence.
      if (_paceHealthyChecks) _armPacedBatch(forceFast: true);
      return;
    }
    _lastByteAt = _now();
    _stallReported = false;
    if (_paceHealthyChecks) _armPacedStall(forceFast: true);
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
