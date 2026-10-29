import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/utils/logger.dart';
import 'package:omi/services/wals/sync_wake_scope.dart';

/// The event that made another recording-transfer pass worthwhile.
///
/// All recording recovery paths use this closed set so a wake can be audited
/// without introducing a second recovery owner.
enum WakeTrigger {
  startup,
  periodic,
  foregrounded,
  connectivityRestored,
  deviceConnected,
  socketReconnected,
  dataStalled,
  cooldownElapsed,
  userRetry,

  /// Periodic in-process wake while recordings wait to upload. Wake sources
  /// are all event-driven otherwise, and a missed event stranded rows for hours.
  watchdog,
}

typedef RecordingTransferPassTimedOut = void Function(WakeTrigger trigger, Duration limit);

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
typedef RecordingTransferTimeoutScheduler = void Function(Duration delay, void Function() callback);
typedef RecordingTransferKeepAlive = Future<void> Function();

/// The single owner for recording recovery.
///
/// Foreground, device reconnect, watchdog and periodic wakes discover and drain
/// backlog. Background wakes run at most two serial passes plus bounded retries;
/// only the OS periodic window fences live capture, and every pass has a hard
/// time limit. A running pass keeps its Android transfer
/// keep-alive until completion or cancellation so screen-off cannot kill
/// BLE/cloud file sync (#5221). It knows no provider or transport details.
class RecordingTransferCoordinator {
  RecordingTransferCoordinator({
    required RecordingTransferPass reconcile,
    required RecordingTransferPass discover,
    required RecordingTransferPass refreshPending,
    required RecordingTransferDrain drain,
    RecordingTransferDrain? drainLiveCapture,
    required bool Function() autoUploadEnabled,
    Stream<bool>? connectivityChanges,
    bool initiallyConnected = true,
    DateTime Function()? clock,
    RecordingTransferCooldownScheduler? scheduleCooldown,
    RecordingTransferTimeoutScheduler? scheduleTimeout,
    void Function()? onTransferAdmitted,
    RecordingTransferKeepAlive? onTransferStarted,
    RecordingTransferKeepAlive? onTransferFinished,
    RecordingTransferPass? onConnectivityRestored,
    Stream<void>? networkChanges,
    bool Function()? hasPendingWork,
    RecordingTransferPassTimedOut? onPassTimedOut,
    this.passTimeLimit = defaultPassTimeLimit,
    this.fencedPassTimeLimit = defaultFencedPassTimeLimit,
    this.watchdogInterval = defaultWatchdogInterval,
  })  : _reconcile = reconcile,
        _discover = discover,
        _refreshPending = refreshPending,
        _drain = drain,
        _drainLiveCapture = drainLiveCapture,
        _autoUploadEnabled = autoUploadEnabled,
        _clock = clock ?? DateTime.now,
        _scheduleCooldown = scheduleCooldown,
        _scheduleTimeout = scheduleTimeout,
        _onTransferAdmitted = onTransferAdmitted,
        _onTransferStarted = onTransferStarted,
        _onTransferFinished = onTransferFinished,
        _onConnectivityRestored = onConnectivityRestored,
        _hasPendingWork = hasPendingWork,
        _onPassTimedOut = onPassTimedOut {
    _configured = true;
    _listenToConnectivity(connectivityChanges, initiallyConnected, networkChanges);
    _armWatchdog();
  }

  RecordingTransferCoordinator._singleton()
      : _reconcile = _noop,
        _discover = _noop,
        _refreshPending = _noop,
        _drain = _skippedDrain,
        _drainLiveCapture = _skippedDrain,
        _autoUploadEnabled = _disabled,
        _clock = DateTime.now,
        passTimeLimit = defaultPassTimeLimit,
        fencedPassTimeLimit = defaultFencedPassTimeLimit,
        watchdogInterval = defaultWatchdogInterval;

  /// Hard limit on one pass. A pendant storage pull of a full ring is ~50 min.
  static const defaultPassTimeLimit = Duration(minutes: 60);

  /// Hard limit on a pass that fences live capture (OS-granted periodic window).
  static const defaultFencedPassTimeLimit = Duration(minutes: 10);
  static const defaultWatchdogInterval = Duration(minutes: 10);

  /// Background retries stop after this many consecutive failures; the
  /// watchdog keeps waking at [watchdogInterval] after that.
  static const _maxBackgroundRetries = 6;

  final Duration passTimeLimit;
  final Duration fencedPassTimeLimit;
  final Duration watchdogInterval;

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
  RecordingTransferDrain? _drainLiveCapture;
  bool Function() _autoUploadEnabled;
  final DateTime Function() _clock;
  RecordingTransferCooldownScheduler? _scheduleCooldown;
  RecordingTransferTimeoutScheduler? _scheduleTimeout;
  void Function()? _onTransferAdmitted;
  RecordingTransferKeepAlive? _onTransferStarted;
  RecordingTransferKeepAlive? _onTransferFinished;
  RecordingTransferPass? _onConnectivityRestored;
  bool Function()? _hasPendingWork;
  RecordingTransferPassTimedOut? _onPassTimedOut;

  StreamSubscription<bool>? _connectivitySubscription;
  StreamSubscription<void>? _networkChangeSubscription;
  Timer? _watchdogTimer;
  Timer? _cooldownTimer;
  Future<void>? _inFlight;
  WakeTrigger? _pendingWake;
  WakeTrigger? _wakeBeforeConfigured;
  bool _configured = false;
  bool _foreground = true;
  bool _wasConnected = true;
  int _failureStreak = 0;
  int _cooldownGeneration = 0;
  int _periodicGeneration = 0;
  bool _periodicDrainInFlight = false;
  int _passGeneration = 0;
  Future<void>? _abandonedPass;

  /// Retire an expired OS window before any further discovery/upload stage.
  /// Returns true only while that window's own drain is running, the one
  /// transfer the window may cancel. A pass another wake started, or a device
  /// transfer the user started, keeps running after the window ends.
  bool cancelPeriodicWake() {
    _periodicGeneration++;
    if (_pendingWake == WakeTrigger.periodic) _pendingWake = null;
    return _periodicDrainInFlight;
  }

  /// Visible to tests and diagnostics; this is not persisted because timers are
  /// foreground-only and startup is always another wake.
  DateTime? nextCooldownAt;

  /// True while a recovery pass (including a chained pending wake) is running.
  /// Cooldown timers start that pass with [unawaited]; observers must use
  /// [waitUntilIdle] rather than a wall-clock sleep.
  bool get hasInFlight => _inFlight != null;

  /// Completes when no recovery pass is running, including wakes chained from
  /// [_pendingWake]. Bounded: a stuck pass fails instead of hanging teardown.
  Future<void> waitUntilIdle({int maxTurns = 32}) async {
    for (var i = 0; i < maxTurns; i++) {
      final active = _inFlight;
      if (active != null) {
        await active;
        continue;
      }
      // `whenComplete` may start a chained wake on a later microtask.
      await Future<void>.delayed(Duration.zero);
      if (_inFlight == null) return;
    }
    throw StateError('RecordingTransferCoordinator did not become idle after $maxTurns turns');
  }

  /// Configures the application singleton after the provider can surface
  /// reconciliation and presentation results. Wakes received before that point
  /// are retained rather than dropped.
  void configure({
    required RecordingTransferPass reconcile,
    required RecordingTransferPass discover,
    required RecordingTransferPass refreshPending,
    required RecordingTransferDrain drain,
    RecordingTransferDrain? drainLiveCapture,
    required bool Function() autoUploadEnabled,
    required Stream<bool> connectivityChanges,
    required bool initiallyConnected,
    void Function()? onTransferAdmitted,
    RecordingTransferKeepAlive? onTransferStarted,
    RecordingTransferKeepAlive? onTransferFinished,
    RecordingTransferPass? onConnectivityRestored,
    Stream<void>? networkChanges,
    bool Function()? hasPendingWork,
    RecordingTransferPassTimedOut? onPassTimedOut,
  }) {
    _reconcile = reconcile;
    _discover = discover;
    _refreshPending = refreshPending;
    _drain = drain;
    _drainLiveCapture = drainLiveCapture;
    _autoUploadEnabled = autoUploadEnabled;
    _onTransferAdmitted = onTransferAdmitted ?? _onTransferAdmitted;
    _onTransferStarted = onTransferStarted ?? _onTransferStarted;
    _onTransferFinished = onTransferFinished ?? _onTransferFinished;
    _onConnectivityRestored = onConnectivityRestored ?? _onConnectivityRestored;
    _hasPendingWork = hasPendingWork ?? _hasPendingWork;
    _onPassTimedOut = onPassTimedOut ?? _onPassTimedOut;
    _configured = true;
    _listenToConnectivity(connectivityChanges, initiallyConnected, networkChanges);
    _armWatchdog();

    final queued = _wakeBeforeConfigured;
    _wakeBeforeConfigured = null;
    if (queued != null) {
      scheduleMicrotask(() => wake(queued));
    }
  }

  void _listenToConnectivity(Stream<bool>? connectivityChanges, bool initiallyConnected, Stream<void>? networkChanges) {
    _connectivitySubscription?.cancel();
    _wasConnected = initiallyConnected;
    _connectivitySubscription = connectivityChanges?.listen((isConnected) {
      final restored = isConnected && !_wasConnected;
      _wasConnected = isConnected;
      if (restored) {
        unawaited(wake(WakeTrigger.connectivityRestored));
      }
    });
    // A wifi -> cellular handover never reports offline, but uploads bound to
    // the old interface are dead and new ones may now succeed.
    _networkChangeSubscription?.cancel();
    _networkChangeSubscription = networkChanges?.listen((_) {
      if (_wasConnected) unawaited(wake(WakeTrigger.connectivityRestored));
    });
  }

  void _armWatchdog() {
    _watchdogTimer?.cancel();
    _watchdogTimer = null;
    if (_hasPendingWork == null) return;
    _watchdogTimer = Timer.periodic(watchdogInterval, (_) => watchdogTick());
  }

  /// Wakes a pass while work is pending and none is running. A pass that
  /// overruns is ended by its own time limit, never by this tick.
  @visibleForTesting
  void watchdogTick() {
    if (_inFlight != null || !_autoUploadEnabled()) return;
    final pending = _hasPendingWork;
    if (pending == null || !pending()) return;
    unawaited(wake(WakeTrigger.watchdog));
  }

  /// Records the foreground state. Retries and the cooldown-end wake keep
  /// running in the background while the process is alive (bounded by
  /// [_maxBackgroundRetries]); a coalesced extra pass stays foreground-only (#5221).
  void setForeground(bool isForeground) {
    _foreground = isForeground;
    if (!isForeground) {
      _pendingWake = null;
    }
  }

  /// Coalesces concurrent events into a single extra serial pass. Five wakes
  /// during one pass therefore run at most two passes and never parallel drains,
  /// including while backgrounded.
  Future<void> wake(WakeTrigger trigger) {
    // Reconnect and periodic background wakes discover device storage and drain
    // backlog inside a sync-only scope. Other eligible background recovery is
    // limited to recent conversation-bound phone WALs. All are bounded in _run.
    if (!_foreground && !_isBackgroundEligible(trigger)) {
      final active = _inFlight;
      if (active != null) return active;
      return Future.value();
    }

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
      if (!_foreground) {
        _pendingWake = null;
        return;
      }
      final lateWake = _pendingWake;
      _pendingWake = null;
      if (lateWake != null) {
        unawaited(wake(lateWake));
      }
    }).ignore();
    return pass;
  }

  bool _isBackgroundEligible(WakeTrigger trigger) =>
      trigger == WakeTrigger.periodic ||
      trigger == WakeTrigger.deviceConnected ||
      trigger == WakeTrigger.connectivityRestored ||
      trigger == WakeTrigger.socketReconnected ||
      trigger == WakeTrigger.dataStalled ||
      trigger == WakeTrigger.cooldownElapsed ||
      trigger == WakeTrigger.watchdog;

  WakeTrigger _preferWake(WakeTrigger? existing, WakeTrigger incoming) {
    if (existing == null) return incoming;
    return _wakePriority(incoming) > _wakePriority(existing) ? incoming : existing;
  }

  int _wakePriority(WakeTrigger trigger) => switch (trigger) {
        WakeTrigger.userRetry => 3,
        WakeTrigger.periodic ||
        WakeTrigger.deviceConnected ||
        WakeTrigger.connectivityRestored ||
        WakeTrigger.watchdog =>
          2,
        WakeTrigger.socketReconnected || WakeTrigger.dataStalled => 1,
        _ => 0,
      };

  Future<void> _run(WakeTrigger firstWake) async {
    // Bind the account before native acquisition can yield. Holding an
    // abandoned pass's native lease below is not admission of another account.
    if (!_abandonedPassRunning) _onTransferAdmitted?.call();
    final started = _onTransferStarted;
    if (started != null) await started();
    try {
      WakeTrigger wake = firstWake;
      var passes = 0;
      do {
        _pendingWake = null;
        await _runPass(wake);
        passes++;
        if (!_foreground) {
          final pending = _pendingWake;
          if (pending == null || passes >= 2 || !_isBackgroundEligible(pending)) {
            _pendingWake = null;
            break;
          }
        }
        wake = _pendingWake ?? wake;
      } while (_pendingWake != null);
    } finally {
      final finished = _onTransferFinished;
      if (finished != null) await finished();
    }
  }

  /// Only the OS-granted periodic window fences live capture. A pendant
  /// reconnect must never wait on its own sync pass to start capturing: a
  /// connected, unsubscribed legacy pendant discards its audio.
  static bool fencesLiveCapture(WakeTrigger trigger) => trigger == WakeTrigger.periodic;

  Future<void> _runPass(WakeTrigger trigger) async {
    final fenced = fencesLiveCapture(trigger);
    final limit = fenced ? fencedPassTimeLimit : passTimeLimit;
    // The limit sits inside the scope, so a hung stage cannot hold the capture
    // fence or `_inFlight` (which every later wake joins) past it.
    final generation = ++_passGeneration;
    Future<void>? running;
    Future<void> body() => _limitedPass(limit, running = _runPassBody(trigger, generation));
    try {
      if (fenced) {
        await SyncWakeScope.run(body);
      } else {
        await body();
      }
    } on TimeoutException {
      Logger.warning('RecordingTransferCoordinator: $trigger pass exceeded ${limit.inMinutes} min; abandoning it');
      // The timeout ends the wait, not the work. Mark the body stale so it
      // stops at its next stage boundary, keep the transfer keep-alive held
      // until it really exits, and let no later pass discover or drain beside it.
      _passGeneration++;
      final abandoned = running;
      if (abandoned != null) await _holdAbandonedPass(abandoned);
      try {
        _onPassTimedOut?.call(trigger, limit);
      } catch (error) {
        Logger.debug('RecordingTransferCoordinator: pass timeout hook failed: $error');
      }
      _scheduleRetry('pass exceeded its time limit');
    }
  }

  /// Races [work] against [limit]. Tests inject [_scheduleTimeout] so the limit
  /// fires at a chosen point instead of on the host's wall clock.
  Future<void> _limitedPass(Duration limit, Future<void> work) {
    final scheduler = _scheduleTimeout;
    if (scheduler == null) return work.timeout(limit);
    final expired = Completer<void>();
    scheduler(limit, () {
      if (!expired.isCompleted) expired.completeError(TimeoutException('pass time limit', limit));
    });
    return Future.any<void>([work, expired.future]);
  }

  Future<void> _holdAbandonedPass(Future<void> abandoned) async {
    final started = _onTransferStarted;
    if (started != null) await started();
    late final Future<void> tracked;
    tracked = abandoned.catchError((Object _) {}).whenComplete(() async {
      if (identical(_abandonedPass, tracked)) _abandonedPass = null;
      final finished = _onTransferFinished;
      if (finished != null) await finished();
    });
    _abandonedPass = tracked;
    tracked.ignore();
  }

  /// An abandoned pass that has not exited yet blocks new discovery and drain
  /// until it really exits, so two `syncAll`s never run at once. Its sync was
  /// cancelled on timeout and every BLE/HTTP await below it is bounded.
  bool get _abandonedPassRunning => _abandonedPass != null;

  Future<void> _runPassBody(WakeTrigger trigger, int generation) async {
    final periodicGeneration = _periodicGeneration;
    bool expired() =>
        generation != _passGeneration || (trigger == WakeTrigger.periodic && periodicGeneration != _periodicGeneration);
    if (_abandonedPassRunning) {
      _scheduleRetry('an abandoned pass has not exited yet');
      return;
    }
    final backlogWake =
        trigger == WakeTrigger.periodic || trigger == WakeTrigger.deviceConnected || trigger == WakeTrigger.watchdog;
    try {
      if (trigger == WakeTrigger.connectivityRestored) {
        await _onConnectivityRestored?.call();
      }
      // Uploaded jobs are resolved before a whole-WAL drain can offer any
      // retryable bytes. `syncAll` only uploads `miss`, preserving job ids.
      // Reconciling only resolves work already on the server, so a failure here
      // must not stop new recordings from uploading — it is retried instead.
      var reconcileFailed = !await _tryReconcile();
      if (expired()) return;
      if (_foreground || backlogWake) {
        await _discover();
      }
      if (expired()) return;
      await _refreshPending();
      if (expired()) return;

      final mayUpload = trigger == WakeTrigger.userRetry || _autoUploadEnabled();
      if (!mayUpload) {
        if (reconcileFailed) _scheduleRetry('reconcile pass failed');
        return;
      }

      final drain = (_foreground || backlogWake) ? _drain : _drainLiveCapture;
      if (drain == null) return;
      final RecordingTransferDrainResult result;
      _periodicDrainInFlight = trigger == WakeTrigger.periodic;
      try {
        result = await drain();
      } finally {
        _periodicDrainInFlight = false;
      }
      if (expired()) return;
      await _refreshPending();
      if (expired()) return;

      // Partial upload success still leaves `uploaded` WALs that need the
      // reconciler before any failure/contention retry path runs.
      if (result.needsReconciliation) {
        reconcileFailed = !await _tryReconcile() || reconcileFailed;
        if (expired()) return;
        await _refreshPending();
        if (expired()) return;
      }

      if (result.failed) {
        _scheduleRetry('eligible WAL upload returned a retryable failure');
        return;
      }
      if (result.contended) {
        _scheduleRetry('eligible WAL drain was contended');
        return;
      }
      if (reconcileFailed) {
        _scheduleRetry('reconcile pass failed');
        return;
      }
      _failureStreak = 0;
    } catch (error, stackTrace) {
      Logger.debug('RecordingTransferCoordinator: $trigger pass failed: $error\n$stackTrace');
      if (expired()) return;
      _scheduleRetry('pass threw while recovering recording transfers');
    }
  }

  /// Runs a reconcile pass, reporting failure instead of propagating it.
  Future<bool> _tryReconcile() async {
    try {
      await _reconcile();
      return true;
    } catch (error, stackTrace) {
      Logger.debug('RecordingTransferCoordinator: reconcile failed, continuing to drain: $error\n$stackTrace');
      return false;
    }
  }

  void _scheduleRetry(String reason) {
    if (!_foreground && _failureStreak >= _maxBackgroundRetries) return;
    final index = _failureStreak.clamp(0, _failureBackoff.length - 1);
    final delay = _failureBackoff[index];
    _failureStreak++;
    nextCooldownAt = _clock().add(delay);
    Logger.debug('RecordingTransferCoordinator: scheduling $reason in ${delay.inSeconds}s');

    _cooldownTimer?.cancel();
    final generation = ++_cooldownGeneration;
    void fire() {
      if (generation != _cooldownGeneration) return;
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
    // Invalidate injected-scheduler callbacks too: those timers are not held
    // in [_cooldownTimer], so cancelling the native timer is not enough.
    _cooldownGeneration++;
    _pendingWake = null;
    nextCooldownAt = null;
    _connectivitySubscription?.cancel();
    _networkChangeSubscription?.cancel();
    _watchdogTimer?.cancel();
    _watchdogTimer = null;
    _cooldownTimer?.cancel();
    _cooldownTimer = null;
  }
}
