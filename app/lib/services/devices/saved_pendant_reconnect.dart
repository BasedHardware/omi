import 'dart:async';

import 'package:flutter/widgets.dart';

import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/debug_log_manager.dart';

/// Both platforms use this schema. Never send the peripheral identifier to analytics.
void recordSavedReconnect(String trigger, int attempt, String result, int disconnectedMs) {
  final properties = <String, dynamic>{
    'trigger': trigger,
    'attempt': attempt,
    'result': result,
    'disconnected_ms': disconnectedMs,
  };
  const TypedEvents().emit(SavedPendantReconnectObserved(
    trigger: SavedPendantReconnectObservedTrigger.values.firstWhere((value) => value.wireName == trigger),
    attempt: attempt,
    result: SavedPendantReconnectObservedResult.values.firstWhere(
      (value) => value.wireName == result.replaceAll(':', '_'),
      orElse: () => SavedPendantReconnectObservedResult.failedConnection,
    ),
    disconnectedMs: disconnectedMs,
  ));
  unawaited(DebugLogManager.logEvent('saved_pendant_reconnect', properties));
}

/// One saved target, one connection attempt, one capped timer. Flags never gate I/O.
class SavedPendantReconnect {
  SavedPendantReconnect({
    required this.target,
    required this.blocked,
    required this.connected,
    required this.connect,
    required this.configure,
    required this.retire,
    required this.observeTarget,
    bool Function()? killed,
    Future<bool> Function()? refreshKilled,
    void Function(String, int, String, int)? record,
  })  : _cachedKilled =
            killed ?? (() => AnalyticsManager().isBooleanFeatureEnabledCached('saved-pendant-reconnect-kill')),
        _refreshKilled = refreshKilled ??
            (killed != null
                ? (() async => killed())
                : (() => AnalyticsManager().refreshBooleanFeatureFlag('saved-pendant-reconnect-kill'))),
        _record = record ?? recordSavedReconnect;

  final String? Function() target;
  final bool Function(String) blocked;
  final bool Function(String) connected;
  final Future<void> Function(String, bool legacy) connect;
  final Future<void> Function(String, bool) configure;
  final Future<void> Function(String) retire;
  final VoidCallback Function(VoidCallback) observeTarget;
  final bool Function() _cachedKilled;
  final Future<bool> Function() _refreshKilled;
  final void Function(String, int, String, int) _record;
  Timer? _timer;
  Timer? _flagTimer;
  AppLifecycleListener? _lifecycle;
  VoidCallback? _removeAdapter;
  VoidCallback? _removeTarget;
  Future<void>? _targetWork;
  final List<String> _retiring = [];
  Future<void>? _refresh;
  String? _ownedTarget;
  int? _runningGeneration;
  bool get _running => _runningGeneration == _generation;
  bool _active = false;
  bool _killActive = false;
  bool get killed => _active ? _killActive : _cachedKilled();
  bool _awaitingOutcome = false;
  int _generation = 0;
  int _lifetime = 0;
  int _attempt = 0;
  int _delaySeconds = 5;
  DateTime? _disconnectedAt;
  String _trigger = 'launch';
  final Set<String> _reported = {};

  void _emit(String trigger, int attempt, String result, int elapsed) {
    // Seven distinct states plus the terminal connected outcome, per episode.
    if (_reported.contains(result) || (_reported.length >= 7 && result != 'connected')) return;
    _reported.add(result);
    _record(trigger, attempt, result, elapsed);
  }

  void start() {
    if (_active) return;
    _active = true;
    _killActive = _cachedKilled();
    _lifecycle = AppLifecycleListener(onResume: () {
      unawaited(refreshPolicy());
      unawaited(ensure('resume'));
    });
    _removeAdapter = BleBridge.instance.addBluetoothStateListener((state) {
      if (state == 'on') unawaited(ensure('adapter_on'));
    });
    _removeTarget = observeTarget(() => unawaited(ensure('launch')));
    // Launch uses cached policy immediately; this request cannot delay connect.
    unawaited(refreshPolicy());
    _flagTimer = Timer.periodic(const Duration(minutes: 5), (_) => unawaited(refreshPolicy()));
  }

  void stop() {
    _active = false;
    _lifetime++;
    _refresh = null;
    _generation++;
    _runningGeneration = null;
    _ownedTarget = null;
    _resetEpisode();
    _timer?.cancel();
    _flagTimer?.cancel();
    _lifecycle?.dispose();
    _lifecycle = null;
    _removeAdapter?.call();
    _removeAdapter = null;
    _removeTarget?.call();
    _removeTarget = null;
  }

  void _resetEpisode() {
    _attempt = 0;
    _delaySeconds = 5;
    _disconnectedAt = null;
    _awaitingOutcome = false;
    _reported.clear();
  }

  Future<void> refreshPolicy() {
    if (_refresh != null) return _refresh!;
    late final Future<void> operation;
    operation = _refreshPolicy().whenComplete(() {
      if (identical(_refresh, operation)) _refresh = null;
    });
    return _refresh = operation;
  }

  Future<void> _refreshPolicy() async {
    final lifetime = _lifetime;
    try {
      final value = await _refreshKilled();
      if (!_active || lifetime != _lifetime || value == _killActive) return;
      _killActive = value;
      _timer?.cancel();
      _generation++; // Fence pending config/connect continuations.
      _runningGeneration = null;
      final id = _ownedTarget;
      if (id != null) await configure(id, !value);
      if (value) {
        _emit(_trigger, _attempt, 'skipped:kill_switch', _elapsed);
      } else {
        unawaited(ensure('resume'));
      }
    } catch (_) {
      // Keep the last cached value. No cache means enabled, including offline launch.
    }
  }

  Future<void>? _syncTarget() {
    final next = target();
    if (next != _ownedTarget) {
      final previous = _ownedTarget;
      _ownedTarget = next;
      _generation++;
      _runningGeneration = null;
      _timer?.cancel();
      _resetEpisode();
      if (previous != null) _retiring.add(previous);
    }
    if (_retiring.isEmpty) return null;
    if (_targetWork != null) return _targetWork;
    late final Future<void> work;
    work = _retireTargets().whenComplete(() {
      if (identical(_targetWork, work)) _targetWork = null;
    });
    return _targetWork = work;
  }

  Future<void> _retireTargets() async {
    while (_retiring.isNotEmpty) {
      final previous = _retiring.first;
      await configure(previous, false);
      await retire(previous);
      _retiring.removeAt(0);
    }
  }

  int get _elapsed => _disconnectedAt == null ? 0 : DateTime.now().difference(_disconnectedAt!).inMilliseconds;

  void stateChanged(String id, bool isConnected) {
    if (!_active || target() != id) return;
    if (isConnected) {
      if (_awaitingOutcome) _emit(_trigger, _attempt, 'connected', _elapsed);
      _timer?.cancel();
      _resetEpisode();
    } else {
      _disconnectedAt ??= DateTime.now();
      _schedule();
    }
  }

  void _schedule() {
    final id = target();
    if (!_active || killed || _running || id == null || blocked(id) || connected(id)) return;
    if (_timer?.isActive == true) return;
    _timer = Timer(Duration(seconds: _delaySeconds), () => unawaited(ensure('backoff')));
    _delaySeconds = (_delaySeconds * 2).clamp(5, 300);
  }

  Future<void> ensure(String trigger) async {
    if (!_active) return;
    try {
      final handoff = _syncTarget();
      if (handoff != null) await handoff;
    } catch (_) {
      _emit(trigger, _attempt, 'failed:connection', _elapsed);
      _schedule(); // Keep failed retirements queued; never connect over an old native owner.
      return;
    }
    final id = _ownedTarget;
    if (!_active || id == null || id != target() || _running) return;
    // Kill mode ignores the new persisted user block, but preserves main's stale-bond guard.
    if (blocked(id)) {
      _emit(trigger, _attempt, 'skipped:user_or_pairing_block', _elapsed);
      return;
    }
    if (connected(id)) return;
    final generation = _generation;
    _runningGeneration = generation;
    _timer?.cancel();
    bool current() => _active && generation == _generation && target() == id && !blocked(id);
    try {
      if (killed) {
        await configure(id, false);
        if (!current()) return;
        _emit(trigger, _attempt, 'skipped:kill_switch', _elapsed);
        if (trigger == 'launch') await connect(id, true);
        return;
      }
      await configure(id, true);
      if (!current()) return;
      _disconnectedAt ??= DateTime.now();
      if (_attempt == 0) _trigger = trigger;
      _attempt++;
      _awaitingOutcome = true;
      _emit(_trigger, _attempt, 'attempted', _elapsed);
      await connect(id, false);
      if (current() && !connected(id)) _emit(_trigger, _attempt, 'failed:not_ready', _elapsed);
    } catch (error) {
      final cause = error is DeviceConnectionException ? error.error : error;
      final reason = cause is BluetoothAdapterUnavailableException
          ? 'adapter_not_ready'
          : cause is TimeoutException
              ? 'timeout'
              : cause is String
                  ? (cause == 'pairing_lost' ? 'pairing_lost' : 'native_connect')
                  : 'connection';
      if (current()) _emit(_trigger, _attempt, 'failed:$reason', _elapsed);
    } finally {
      if (_runningGeneration == generation) _runningGeneration = null;
      if (current()) _schedule();
    }
  }
}
