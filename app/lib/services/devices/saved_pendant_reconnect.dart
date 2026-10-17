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

/// One owner, one timer, no scans. A failed launch does not revoke user intent.
class SavedPendantReconnect {
  SavedPendantReconnect({
    required this.target,
    required this.blocked,
    required this.connected,
    required this.connect,
    required this.configure,
    Future<bool> Function()? killed,
    void Function(String, int, String, int)? record,
  })  : _killed = killed ??
            (() async {
              await AnalyticsManager().reloadFeatureFlags();
              return AnalyticsManager().isBooleanFeatureEnabled('saved-pendant-reconnect-kill');
            }),
        _record = record ?? recordSavedReconnect;

  final String? Function() target;
  final bool Function(String) blocked;
  final bool Function(String) connected;
  final Future<void> Function(String) connect;
  final Future<void> Function(String, bool) configure;
  final Future<bool> Function() _killed;
  final void Function(String, int, String, int) _record;
  Timer? _timer;
  AppLifecycleListener? _lifecycle;
  VoidCallback? _removeAdapter;
  int? _runningGeneration;
  bool get _running => _runningGeneration == _generation;
  bool _active = false;
  bool _killActive = false;
  int _generation = 0;
  int _attempt = 0;
  int _delaySeconds = 5;
  DateTime? _disconnectedAt;
  String _trigger = 'launch';

  void start() {
    if (_active) return;
    _active = true;
    _lifecycle = AppLifecycleListener(onResume: () => unawaited(ensure('resume')));
    _removeAdapter = BleBridge.instance.addBluetoothStateListener((state) {
      if (state == 'on') unawaited(ensure('adapter_on'));
    });
  }

  void stop() {
    _active = false;
    _generation++;
    _runningGeneration = null;
    _attempt = 0;
    _delaySeconds = 5;
    _disconnectedAt = null;
    _killActive = false;
    _timer?.cancel();
    _lifecycle?.dispose();
    _lifecycle = null;
    _removeAdapter?.call();
    _removeAdapter = null;
  }

  int get _elapsed => _disconnectedAt == null ? 0 : DateTime.now().difference(_disconnectedAt!).inMilliseconds;

  void stateChanged(String id, bool isConnected) {
    if (!_active || target() != id) return;
    if (isConnected) {
      _record(_trigger, _attempt, 'connected', _elapsed);
      _timer?.cancel();
      _disconnectedAt = null;
      _delaySeconds = 5;
    } else {
      _disconnectedAt ??= DateTime.now();
      _schedule();
    }
  }

  void _schedule() {
    final id = target();
    if (!_active || _killActive || _running || id == null || blocked(id) || connected(id)) return;
    if (_timer?.isActive == true) return;
    _timer = Timer(Duration(seconds: _delaySeconds), () => unawaited(ensure('backoff')));
    _delaySeconds = (_delaySeconds * 2).clamp(5, 300);
  }

  Future<void> ensure(String trigger) async {
    final id = target();
    if (!_active || id == null || _running) return;
    if (blocked(id)) {
      _record(trigger, _attempt, 'skipped:user_or_pairing_block', _elapsed);
      return;
    }
    if (connected(id)) return;
    final generation = _generation;
    _runningGeneration = generation;
    _timer?.cancel();
    bool current() => _active && generation == _generation && target() == id && !blocked(id);
    try {
      // Unreachable, missing, or timed-out flag means ON. Only true kills it.
      final killed =
          await _killed().timeout(const Duration(seconds: 2), onTimeout: () => false).catchError((_) => false);
      if (!current()) return;
      _killActive = killed;
      await configure(id, !killed);
      if (!current()) return;
      if (killed) {
        _record(trigger, _attempt, 'skipped:kill_switch', _elapsed);
        if (trigger == 'launch') await connect(id); // Preserve the legacy launch attempt.
        return;
      }
      _disconnectedAt ??= DateTime.now();
      _trigger = trigger;
      _attempt++;
      _record(trigger, _attempt, 'attempted', _elapsed);
      await connect(id);
      if (!current()) return;
      if (!connected(id)) _record(trigger, _attempt, 'failed:not_ready', _elapsed);
    } catch (error) {
      final cause = error is DeviceConnectionException ? error.error : error;
      final reason = cause is BluetoothAdapterUnavailableException
          ? 'adapter_not_ready'
          : cause is TimeoutException
              ? 'timeout'
              : cause is String
                  ? (cause == 'pairing_lost' ? 'pairing_lost' : 'native_connect')
                  : 'connection';
      if (current()) _record(trigger, _attempt, 'failed:$reason', _elapsed);
    } finally {
      if (_runningGeneration == generation) _runningGeneration = null;
      if (current() && !_killActive) _schedule();
    }
  }
}
