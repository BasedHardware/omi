import 'dart:async';

import 'package:omi/utils/logger.dart';

/// The event that made another foreground recording-transfer pass worthwhile.
///
/// All recording recovery paths use this closed set so a wake can be audited
/// without introducing a second recovery owner.
enum WakeTrigger { startup, foregrounded, connectivityRestored, deviceConnected, cooldownElapsed, userRetry }

/// Result reported by the production drain seam.
///
/// A local WAL upload can fail per batch and still return normally from
/// `syncAll`. [failed] makes that durable retry signal explicit without
/// changing WAL state transitions: failed WALs remain retryable (`miss`).
class RecordingTransferDrainResult {
  const RecordingTransferDrainResult({
    required this.attempted,
    required this.failed,
    required this.needsReconciliation,
    this.contended = false,
  });

  /// Nothing eligible to drain (empty backlog). Not a retry signal.
  const RecordingTransferDrainResult.skipped()
      : attempted = false,
        failed = false,
        needsReconciliation = false,
        contended = false;

  /// Drain could not run because another sync owned the seam. Retry later.
  const RecordingTransferDrainResult.contended()
      : attempted = false,
        failed = false,
        needsReconciliation = false,
        contended = true;

  final bool attempted;
  final bool failed;
  final bool needsReconciliation;
  final bool contended;
}

typedef RecordingTransferPass = Future<void> Function();
typedef RecordingTransferDrain = Future<RecordingTransferDrainResult> Function();
typedef RecordingTransferCooldownScheduler = void Function(Duration delay, void Function() callback);

/// The single foreground owner for recording recovery.
///
/// It deliberately knows no provider or transport details. Production wires
/// the seams once, while tests use the same coordinator with fake connectivity,
/// time, reconciliation, and drain functions.
class RecordingTransferCoordinator {
  RecordingTransferCoordinator({
    required RecordingTransferPass reconcile,
    required RecordingTransferPass discover,
    required RecordingTransferPass refreshPending,
    required RecordingTransferDrain drain,
    required bool Function() autoUploadEnabled,
    Stream<bool>? connectivityChanges,
    bool initiallyConnected = true,
    DateTime Function()? clock,
    RecordingTransferCooldownScheduler? scheduleCooldown,
  })  : _reconcile = reconcile,
        _discover = discover,
        _refreshPending = refreshPending,
        _drain = drain,
        _autoUploadEnabled = autoUploadEnabled,
        _clock = clock ?? DateTime.now,
        _scheduleCooldown = scheduleCooldown {
    _configured = true;
    _listenToConnectivity(connectivityChanges, initiallyConnected);
  }

  RecordingTransferCoordinator._singleton()
      : _reconcile = _noop,
        _discover = _noop,
        _refreshPending = _noop,
        _drain = _skippedDrain,
        _autoUploadEnabled = _disabled,
        _clock = DateTime.now;

  static final RecordingTransferCoordinator instance = RecordingTransferCoordinator._singleton();

  static Future<void> _noop() async {}
  static Future<RecordingTransferDrainResult> _skippedDrain() async => const RecordingTransferDrainResult.skipped();
  static bool _disabled() => false;

  static const List<Duration> _failureBackoff = [
    Duration(seconds: 5),
    Duration(seconds: 10),
    Duration(seconds: 20),
    Duration(seconds: 60),
  ];

  RecordingTransferPass _reconcile;
  RecordingTransferPass _discover;
  RecordingTransferPass _refreshPending;
  RecordingTransferDrain _drain;
  bool Function() _autoUploadEnabled;
  final DateTime Function() _clock;
  RecordingTransferCooldownScheduler? _scheduleCooldown;

  StreamSubscription<bool>? _connectivitySubscription;
  Timer? _cooldownTimer;
  Future<void>? _inFlight;
  WakeTrigger? _pendingWake;
  WakeTrigger? _wakeBeforeConfigured;
  bool _configured = false;
  bool _foreground = true;
  bool _wasConnected = true;
  int _failureStreak = 0;
  int _cooldownGeneration = 0;

  /// Visible to tests and diagnostics; this is not persisted because timers are
  /// foreground-only and startup is always another wake.
  DateTime? nextCooldownAt;

  /// Configures the application singleton after the provider can surface
  /// reconciliation and presentation results. Wakes received before that point
  /// are retained rather than dropped.
  void configure({
    required RecordingTransferPass reconcile,
    required RecordingTransferPass discover,
    required RecordingTransferPass refreshPending,
    required RecordingTransferDrain drain,
    required bool Function() autoUploadEnabled,
    required Stream<bool> connectivityChanges,
    required bool initiallyConnected,
  }) {
    _reconcile = reconcile;
    _discover = discover;
    _refreshPending = refreshPending;
    _drain = drain;
    _autoUploadEnabled = autoUploadEnabled;
    _configured = true;
    _listenToConnectivity(connectivityChanges, initiallyConnected);

    final queued = _wakeBeforeConfigured;
    _wakeBeforeConfigured = null;
    if (queued != null) {
      scheduleMicrotask(() => wake(queued));
    }
  }

  void _listenToConnectivity(Stream<bool>? connectivityChanges, bool initiallyConnected) {
    _connectivitySubscription?.cancel();
    _wasConnected = initiallyConnected;
    _connectivitySubscription = connectivityChanges?.listen((isConnected) {
      final restored = isConnected && !_wasConnected;
      _wasConnected = isConnected;
      if (restored) {
        unawaited(wake(WakeTrigger.connectivityRestored));
      }
    });
  }

  /// Stops foreground-only retry timers while the app is backgrounded. The
  /// persisted WAL state is picked up by the next foreground or startup wake.
  void setForeground(bool isForeground) {
    _foreground = isForeground;
    if (!isForeground) {
      _cooldownGeneration++;
      _cooldownTimer?.cancel();
      _cooldownTimer = null;
      nextCooldownAt = null;
    }
  }

  /// Coalesces concurrent events into a single extra serial pass. Five wakes
  /// during one pass therefore run at most two passes and never parallel drains.
  Future<void> wake(WakeTrigger trigger) {
    // Recovery is foreground-only. Persisted WAL state is recovered by the
    // foreground wake, so background connectivity/device callbacks must not
    // start discovery or a whole-WAL drain.
    if (!_foreground) return Future.value();

    if (!_configured) {
      _wakeBeforeConfigured = _preferWake(_wakeBeforeConfigured, trigger);
      return Future.value();
    }

    final active = _inFlight;
    if (active != null) {
      _pendingWake = _preferWake(_pendingWake, trigger);
      return active;
    }

    final pass = _run(trigger);
    _inFlight = pass;
    pass.whenComplete(() {
      if (!identical(_inFlight, pass)) return;
      _inFlight = null;
      final lateWake = _pendingWake;
      _pendingWake = null;
      if (lateWake != null) {
        unawaited(wake(lateWake));
      }
    });
    return pass;
  }

  WakeTrigger _preferWake(WakeTrigger? existing, WakeTrigger incoming) {
    if (existing == WakeTrigger.userRetry || incoming != WakeTrigger.userRetry) {
      return existing ?? incoming;
    }
    return incoming;
  }

  Future<void> _run(WakeTrigger firstWake) async {
    WakeTrigger wake = firstWake;
    do {
      _pendingWake = null;
      await _runPass(wake);
      wake = _pendingWake ?? wake;
    } while (_pendingWake != null);
  }

  Future<void> _runPass(WakeTrigger trigger) async {
    try {
      // Uploaded jobs are resolved before a whole-WAL drain can offer any
      // retryable bytes. `syncAll` only uploads `miss`, preserving job ids.
      await _reconcile();
      await _discover();
      await _refreshPending();

      final mayUpload = trigger == WakeTrigger.userRetry || _autoUploadEnabled();
      if (!mayUpload) return;

      final result = await _drain();
      await _refreshPending();

      // Partial upload success still leaves `uploaded` WALs that need the
      // reconciler before any failure/contention retry path runs.
      if (result.needsReconciliation) {
        await _reconcile();
        await _refreshPending();
      }

      if (result.failed) {
        _scheduleRetry('eligible WAL upload returned a retryable failure');
        return;
      }
      if (result.contended) {
        _scheduleRetry('eligible WAL drain was contended');
        return;
      }
      _failureStreak = 0;
    } catch (error, stackTrace) {
      Logger.debug('RecordingTransferCoordinator: $trigger pass failed: $error\n$stackTrace');
      _scheduleRetry('pass threw while recovering recording transfers');
    }
  }

  void _scheduleRetry(String reason) {
    if (!_foreground) return;
    final index = _failureStreak.clamp(0, _failureBackoff.length - 1);
    final delay = _failureBackoff[index];
    _failureStreak++;
    nextCooldownAt = _clock().add(delay);
    Logger.debug('RecordingTransferCoordinator: scheduling $reason in ${delay.inSeconds}s');

    _cooldownTimer?.cancel();
    final generation = ++_cooldownGeneration;
    void fire() {
      if (!_foreground || generation != _cooldownGeneration) return;
      _cooldownTimer = null;
      nextCooldownAt = null;
      unawaited(wake(WakeTrigger.cooldownElapsed));
    }

    final scheduler = _scheduleCooldown;
    if (scheduler != null) {
      scheduler(delay, fire);
    } else {
      _cooldownTimer = Timer(delay, fire);
    }
  }

  void dispose() {
    _connectivitySubscription?.cancel();
    _cooldownTimer?.cancel();
    _cooldownTimer = null;
  }
}
