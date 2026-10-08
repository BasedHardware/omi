import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum PhoneBatterySamplingTrigger {
  lifecycleForeground('lifecycle_foreground'),
  lifecycleBackground('lifecycle_background'),
  timerForeground('timer_foreground');

  const PhoneBatterySamplingTrigger(this.wireName);
  final String wireName;
}

/// Phone snapshots only. The pendant's health rollup is a separate signal.
/// Owns one foreground timer, cancelled on every departure from resumed and
/// synchronously on opt-out. Native reads are snapshots, never subscriptions.
class PhoneBatterySampleTelemetry with WidgetsBindingObserver {
  PhoneBatterySampleTelemetry({
    Future<Map<String, Object?>?> Function()? readBattery,
    Future<SharedPreferences> Function()? preferences,
    ValueListenable<bool>? trackingConsent,
    void Function(String, Map<String, dynamic>)? emit,
    DateTime Function()? now,
    bool? supported,
  })  : _readBattery = readBattery ?? (() => _channel.invokeMapMethod<String, Object?>('read')),
        _preferences = preferences ?? SharedPreferences.getInstance,
        _consent = trackingConsent ?? AnalyticsManager.trackingConsent,
        _emit = emit ?? ((name, properties) => PlatformManager.instance.analytics.track(name, properties: properties)),
        _now = now ?? DateTime.now,
        _supported = supported ?? (Platform.isAndroid || Platform.isIOS);

  static const eventName = 'Phone Battery Sample';
  static const _channel = MethodChannel('com.omi/phone_battery');
  static const lastSampleKey = 'phone_battery_last_sample_ms';
  static const minimumInterval = Duration(minutes: 5);
  static const foregroundInterval = Duration(minutes: 15);
  final Future<Map<String, Object?>?> Function() _readBattery;
  final Future<SharedPreferences> Function() _preferences;
  final ValueListenable<bool> _consent;
  final void Function(String, Map<String, dynamic>) _emit;
  final DateTime Function() _now;
  final bool _supported;
  SharedPreferences? _prefs;
  Timer? _timer;
  bool _started = false;
  bool _disposed = false;
  bool _inFlight = false;
  bool _backgrounded = true;
  bool _persistedConsent = true;
  int _consentGeneration = 0;
  AppLifecycleState _state = AppLifecycleState.detached;

  @visibleForTesting
  bool get hasForegroundTimer => _timer?.isActive ?? false;

  Future<void> start() async {
    if (_started || _disposed || !_supported) return;
    _started = true;
    _state = WidgetsBinding.instance.lifecycleState ?? AppLifecycleState.detached;
    WidgetsBinding.instance.addObserver(this);
    _consent.addListener(_onConsentChanged);
    try {
      _prefs = await _preferences();
      if (_disposed) return;
      _persistedConsent =
          _consentGeneration > 0 ? _consent.value : (_prefs!.getBool('product_analytics_enabled') ?? true);
      // Analytics initialization is asynchronous. Check persisted consent before
      // starting any timer, even while the manager still has its default value.
      didChangeAppLifecycleState(_state);
    } catch (_) {
      debugPrint('Phone battery telemetry: preferences unavailable');
    }
  }

  bool get _enabled => !_disposed && _prefs != null && _consent.value && _persistedConsent;

  void _onConsentChanged() {
    _consentGeneration++;
    _timer?.cancel();
    _timer = null;
    _persistedConsent = _consent.value;
    _updateTimer();
  }

  void _updateTimer() {
    _timer?.cancel();
    _timer = null;
    if (!_enabled || _state != AppLifecycleState.resumed) return;
    _timer = Timer.periodic(foregroundInterval, (_) {
      if (!_enabled || _state != AppLifecycleState.resumed) {
        _timer?.cancel();
        _timer = null;
        return;
      }
      unawaited(_sample(PhoneBatterySamplingTrigger.timerForeground));
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _state = state;
    _updateTimer();
    if (_prefs == null) return;
    if (state == AppLifecycleState.resumed) {
      if (!_backgrounded) return;
      _backgrounded = false;
      unawaited(_sample(PhoneBatterySamplingTrigger.lifecycleForeground));
    } else if (state == AppLifecycleState.hidden || state == AppLifecycleState.paused) {
      if (_backgrounded) return;
      _backgrounded = true;
      unawaited(_sample(PhoneBatterySamplingTrigger.lifecycleBackground));
    }
  }

  Future<void> _sample(PhoneBatterySamplingTrigger trigger) async {
    if (!_enabled || _inFlight) return;
    _inFlight = true;
    final generation = _consentGeneration;
    try {
      final now = _now();
      final previousMs = _prefs!.getInt(lastSampleKey);
      final elapsed = previousMs == null ? null : now.difference(DateTime.fromMillisecondsSinceEpoch(previousMs));
      // A backwards wall-clock jump also suppresses sampling until the clock
      // catches up, rather than producing a negative elapsed duration.
      if (elapsed != null && elapsed < minimumInterval) return;
      final battery = await _readBattery();
      if (!_enabled || generation != _consentGeneration) return;
      final level = battery?['battery_level'];
      final charging = battery?['battery_charging'];
      if (level is! int || level < 0 || level > 100 || charging is! bool) {
        debugPrint('Phone battery telemetry: battery snapshot unknown');
        return;
      }
      final saver = battery?['os_battery_saver'];
      if (!await _prefs!.setInt(lastSampleKey, now.millisecondsSinceEpoch)) {
        debugPrint('Phone battery telemetry: timestamp persistence failed');
        return;
      }
      if (!_enabled || generation != _consentGeneration) return;
      _emit(eventName, {
        'battery_level': level,
        'battery_charging': charging,
        if (elapsed != null) 'seconds_since_previous_sample': elapsed.inMilliseconds / 1000.0,
        'sampling_trigger': trigger.wireName,
        if (saver is bool) 'os_battery_saver': saver,
      });
    } catch (_) {
      debugPrint('Phone battery telemetry: sample unavailable');
    } finally {
      _inFlight = false;
    }
  }

  void dispose() {
    _disposed = true;
    _timer?.cancel();
    _timer = null;
    if (_started) {
      WidgetsBinding.instance.removeObserver(this);
      _consent.removeListener(_onConsentChanged);
    }
  }
}
