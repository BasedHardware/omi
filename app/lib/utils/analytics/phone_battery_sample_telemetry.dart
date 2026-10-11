import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum PhoneBatterySamplingTrigger {
  lifecycleForeground('lifecycle_foreground'),
  lifecycleBackground('lifecycle_background'),
  timerForeground('timer_foreground');

  const PhoneBatterySamplingTrigger(this.wireName);
  final String wireName;
}

/// Phone snapshots only. Reuses the foreground timer and lifecycle callbacks.
/// The locally stored baseline belongs to one identity on this installation;
/// it survives upgrades, but never consent or identity changes. No native
/// subscriptions are opened. Unsupported thermal/charging coverage stays null.
class PhoneBatterySampleTelemetry with WidgetsBindingObserver {
  PhoneBatterySampleTelemetry({
    Future<Map<String, Object?>?> Function()? readBattery,
    Future<String?> Function()? readBuild,
    Future<SharedPreferences> Function()? preferences,
    ValueListenable<bool>? trackingConsent,
    ValueListenable<int>? identityChanges,
    String? Function()? identity,
    ({String source, String mode}) Function()? captureContext,
    void Function(String, Map<String, dynamic>)? emit,
    DateTime Function()? now,
    int Function()? monotonicMs,
    bool? supported,
  })  : _readBattery = readBattery ?? (() => _channel.invokeMapMethod<String, Object?>('read')),
        _readBuild = readBuild ?? (() async => (await PackageInfo.fromPlatform()).buildNumber),
        _preferences = preferences ?? SharedPreferences.getInstance,
        _consent = trackingConsent ?? AnalyticsManager.trackingConsent,
        _identityChanges = identityChanges ?? AnalyticsManager.identityChanges,
        _identity = identity ?? (() => AnalyticsManager.currentIdentity),
        _captureContext = captureContext ?? (() => (source: 'unknown', mode: 'unknown')),
        _emit = emit ?? ((name, properties) => PlatformManager.instance.analytics.track(name, properties: properties)),
        _now = now ?? DateTime.now,
        _monotonicMs = monotonicMs ?? _elapsedClock(),
        _supported = supported ?? (Platform.isAndroid || Platform.isIOS);

  bool get _usesAndroidElapsed => defaultTargetPlatform == TargetPlatform.android;

  int _snapshotElapsed(Map<String, Object?>? battery) {
    if (!_usesAndroidElapsed) return _monotonicMs();
    final elapsed = battery?['elapsed_realtime_ms'];
    if (elapsed is! int || elapsed < 0) throw StateError('Android elapsed clock unavailable');
    return elapsed;
  }

  static int Function() _elapsedClock() {
    final clock = Stopwatch()..start();
    return () => clock.elapsedMilliseconds;
  }

  static const clockSkewTolerance = Duration(seconds: 90);
  static const eventName = 'Phone Battery Sample';
  static const _channel = MethodChannel('com.omi/phone_battery');
  static const lastSampleKey = 'phone_battery_last_sample_ms';
  static const snapshotKey = 'phone_battery_previous_snapshot_v2';
  static const buildFirstRunKey = 'phone_battery_build_first_run_v2';
  static const minimumInterval = Duration(minutes: 5);
  static const foregroundInterval = Duration(minutes: 15);
  final Future<Map<String, Object?>?> Function() _readBattery;
  final Future<String?> Function() _readBuild;
  final Future<SharedPreferences> Function() _preferences;
  final ValueListenable<bool> _consent;
  final ValueListenable<int> _identityChanges;
  final String? Function() _identity;
  final ({String source, String mode}) Function() _captureContext;
  final void Function(String, Map<String, dynamic>) _emit;
  final DateTime Function() _now;
  final int Function() _monotonicMs;
  final bool _supported;
  SharedPreferences? _prefs;
  Map<String, dynamic>? _previous;
  Future<void>? _writes;
  Future<void> _clockTransitions = Future.value();
  Timer? _timer;
  bool _started = false;
  bool _disposed = false;
  bool _inFlight = false;
  bool _backgrounded = true;
  bool _persistedConsent = true;
  bool _identityChanged = false;
  int _generation = 0;
  int _consentGeneration = 0;
  int? _foregroundSinceMs;
  int _foregroundMs = 0;
  bool _foregroundCoverage = false;
  bool _intervalClockInvalid = false;
  int _clockInvalidGeneration = 0;
  int? _clockWallMs;
  int? _clockElapsedMs;
  int? _chargingObservedAtMs;
  AppLifecycleState _state = AppLifecycleState.detached;

  @visibleForTesting
  bool get hasForegroundTimer => _timer?.isActive ?? false;

  String? get _identityFence {
    final identity = _identity();
    return identity == null || identity.isEmpty ? null : sha256.convert(utf8.encode(identity)).toString();
  }

  static Map<String, dynamic>? _record(String? raw) {
    try {
      final decoded = raw == null ? null : jsonDecode(raw);
      return decoded is Map<String, dynamic> ? decoded : null;
    } catch (_) {
      return null;
    }
  }

  Future<String?> _observedBuild() async {
    try {
      final build = await _readBuild();
      return build == null || build.isEmpty || build == 'unknown' ? null : build;
    } catch (_) {
      return null;
    }
  }

  Future<void> start() async {
    if (_started || _disposed || !_supported) return;
    _started = true;
    _state = WidgetsBinding.instance.lifecycleState ?? AppLifecycleState.detached;
    WidgetsBinding.instance.addObserver(this);
    _consent.addListener(_onConsentChanged);
    _identityChanges.addListener(_onIdentityChanged);
    try {
      _prefs = await _preferences();
      if (_disposed) return;
      _persistedConsent =
          _consentGeneration > 0 ? _consent.value : (_prefs!.getBool('product_analytics_enabled') ?? true);
      final previous = _record(_prefs!.getString(snapshotKey));
      if (!_enabled || _generation > 0) {
        await _clearBaseline();
      } else if (previous != null) {
        if (_identityFence == null || previous['identity'] != _identityFence) {
          _identityChanged = true;
          await _clearBaseline();
        } else if (previous['at_ms'] is int &&
            previous['level'] is int &&
            (previous['level'] as int) >= 0 &&
            (previous['level'] as int) <= 100 &&
            previous['charging'] is bool) {
          _previous = previous;
        }
      }
      // Persist the observed build's first run even when a battery read fails.
      if (_enabled) {
        unawaited(_observeBuild(await _observedBuild(), _now().millisecondsSinceEpoch).catchError((Object _) => null));
      }
      if (!_disposed) didChangeAppLifecycleState(_state);
    } catch (_) {
      debugPrint('Phone battery telemetry: preferences/build unavailable');
    }
  }

  bool get _enabled => !_disposed && _prefs != null && _consent.value && _persistedConsent;

  Future<void> _write(Future<void> Function() action) {
    final next = _writes == null ? action() : _writes!.then((_) => action());
    _writes = next.catchError((Object _) {});
    return next;
  }

  Future<void> _clearBaseline() => _write(() async {
        final prefs = _prefs;
        if (prefs == null) return;
        await prefs.remove(snapshotKey);
        await prefs.remove(lastSampleKey);
      });

  void _invalidateBaseline({required bool identityChanged}) {
    _generation++;
    _previous = null;
    _identityChanged = identityChanged;
    _foregroundCoverage = false;
    _foregroundMs = 0;
    _intervalClockInvalid = false;
    _clockWallMs = _usesAndroidElapsed ? null : _now().millisecondsSinceEpoch;
    _clockElapsedMs = _usesAndroidElapsed ? null : _monotonicMs();
    _foregroundSinceMs = _state == AppLifecycleState.resumed ? _clockElapsedMs : null;
    _chargingObservedAtMs = null;
    unawaited(_clearBaseline().catchError((Object _) {
      debugPrint('Phone battery telemetry: baseline cleanup unavailable');
    }));
  }

  void _onIdentityChanged() => _invalidateBaseline(identityChanged: true);

  void _onConsentChanged() {
    _consentGeneration++;
    _persistedConsent = _consent.value;
    _invalidateBaseline(identityChanged: false);
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

  // Observe every transition, including background spans. Wall time is only
  // trustworthy when it agrees with the continuously running elapsed clock.
  void _observeClocks(int wallMs, int elapsedMs) {
    final priorWall = _clockWallMs;
    final priorElapsed = _clockElapsedMs;
    if (priorWall != null && priorElapsed != null) {
      final wallDelta = wallMs - priorWall;
      final elapsedDelta = elapsedMs - priorElapsed;
      if (wallDelta < 0 || elapsedDelta < 0 || (wallDelta - elapsedDelta).abs() > clockSkewTolerance.inMilliseconds) {
        _intervalClockInvalid = true;
        _clockInvalidGeneration++;
      }
      if (_foregroundSinceMs != null && elapsedDelta >= 0) {
        _foregroundMs += elapsedDelta;
      }
    }
    _clockWallMs = wallMs;
    _clockElapsedMs = elapsedMs;
    if (_foregroundSinceMs != null) _foregroundSinceMs = elapsedMs;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (_usesAndroidElapsed && _enabled) {
      // Android Stopwatch excludes suspend. Read the existing snapshot even for
      // throttled transitions so a wall-clock rollback cannot hide between samples.
      final generation = _generation;
      final observation = () async {
        try {
          final battery = await _readBattery();
          return (wall: _now().millisecondsSinceEpoch, elapsed: _snapshotElapsed(battery));
        } catch (_) {
          return null;
        }
      }();
      _clockTransitions = _clockTransitions.then((_) async {
        try {
          final clock = await observation;
          if (_disposed || generation != _generation) return;
          if (clock == null) throw StateError('Android elapsed clock unavailable');
          _observeClocks(clock.wall, clock.elapsed);
          _foregroundSinceMs = state == AppLifecycleState.resumed ? clock.elapsed : null;
        } catch (_) {
          // Never substitute the suspend-exclusive Stopwatch for a missing read.
          if (_disposed || generation != _generation) return;
          _intervalClockInvalid = true;
          _clockInvalidGeneration++;
          _clockWallMs = null;
          _clockElapsedMs = null;
          _foregroundSinceMs = null;
        }
      });
    } else if (!_usesAndroidElapsed) {
      final atMs = _now().millisecondsSinceEpoch;
      final elapsedMs = _monotonicMs();
      _observeClocks(atMs, elapsedMs);
      _foregroundSinceMs = state == AppLifecycleState.resumed ? elapsedMs : null;
    }
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

  /// May be called by an already delivered *phone* charging callback. Endpoints
  /// never call this. No callback observed means null, never continuous coverage.
  void recordPassiveCharging(bool charging) {
    if (_enabled && charging && _previous != null) _chargingObservedAtMs = _now().millisecondsSinceEpoch;
  }

  static String? _thermalState(Object? value) => const {
        'nominal',
        'fair',
        'serious',
        'critical',
        'none',
        'light',
        'moderate',
        'severe',
        'emergency',
        'shutdown',
      }.contains(value)
          ? value as String
          : null;

  Future<double?> _observeBuild(String? build, int atMs) async {
    if (build == null || build.isEmpty || build == 'unknown') return null;
    double? seconds;
    await _write(() async {
      final old = _record(_prefs!.getString(buildFirstRunKey));
      final first = old?['build'] == build && old?['first_ms'] is int ? old!['first_ms'] as int : atMs;
      // A high-water mark keeps age monotone even across wall-clock rollback.
      final priorHigh = old?['build'] == build && old?['high_ms'] is int ? old!['high_ms'] as int : first;
      final high = atMs > priorHigh ? atMs : priorHigh;
      if (!await _prefs!
          .setString(buildFirstRunKey, jsonEncode({'build': build, 'first_ms': first, 'high_ms': high}))) {
        return;
      }
      seconds = (high - first) / 1000.0;
    });
    return seconds;
  }

  Future<void> _sample(PhoneBatterySamplingTrigger trigger) async {
    if (!_enabled || _inFlight) return;
    _inFlight = true;
    final generation = _generation;
    final identity = _identityFence;
    try {
      await _clockTransitions;
      if (!_enabled || generation != _generation || identity != _identityFence) return;
      final throttleMs = _prefs!.getInt(lastSampleKey);
      final throttleElapsed = throttleMs == null ? null : _now().millisecondsSinceEpoch - throttleMs;
      // Preserve the original five-minute throttle, including backwards jumps.
      if (throttleElapsed != null && throttleElapsed < minimumInterval.inMilliseconds) return;
      final build = await _observedBuild();
      final battery = await _readBattery();
      final atMs = _now().millisecondsSinceEpoch;
      if (!_enabled || generation != _generation || identity != _identityFence) return;
      final level = battery?['battery_level'];
      final charging = battery?['battery_charging'];
      if (level is! int || level < 0 || level > 100 || charging is! bool) {
        debugPrint('Phone battery telemetry: battery snapshot unknown');
        return;
      }
      final previous = _previous;
      final previousMs = previous?['at_ms'] as int?;
      final elapsedMs = previousMs == null ? null : atMs - previousMs;
      final referenceMs = _snapshotElapsed(battery);
      _observeClocks(atMs, referenceMs);
      if (_usesAndroidElapsed) {
        _foregroundSinceMs = _state == AppLifecycleState.resumed ? referenceMs : null;
      }
      final clockGenerationAtSample = _clockInvalidGeneration;
      final clockInvalid = elapsedMs != null && (elapsedMs <= 0 || _intervalClockInvalid);
      final validity = _identityChanged
          ? 'identity_changed'
          : previous == null
              ? 'no_baseline'
              : clockInvalid
                  ? 'clock_invalid'
                  : build == null || previous['build'] == null
                      ? 'no_baseline'
                      : previous['build'] == build
                          ? 'same_build'
                          : 'build_changed';
      final foregroundMsAtSample = _foregroundMs;
      final foregroundSeconds =
          previous != null && _foregroundCoverage && !clockInvalid ? _foregroundMs / 1000.0 : null;
      final chargingObserved = previousMs != null &&
          _chargingObservedAtMs != null &&
          _chargingObservedAtMs! > previousMs &&
          _chargingObservedAtMs! < atMs;
      final capture = _captureContext();
      final lifecycle = _state.name;
      final buildAge = await _observeBuild(build, atMs);
      final next = {'identity': identity, 'at_ms': atMs, 'level': level, 'charging': charging, 'build': build};
      var persisted = false;
      await _write(() async {
        if (!_enabled || generation != _generation || identity != _identityFence) return;
        if (identity != null && !await _prefs!.setString(snapshotKey, jsonEncode(next))) return;
        persisted = await _prefs!.setInt(lastSampleKey, atMs);
      });
      if (!persisted || !_enabled || generation != _generation || identity != _identityFence) return;
      _emit(eventName, {
        'schema_version': 2,
        'battery_level': level,
        'battery_charging': charging,
        if (throttleMs != null && atMs >= throttleMs) 'seconds_since_previous_sample': (atMs - throttleMs) / 1000.0,
        'sampling_trigger': trigger.wireName,
        if (battery?['os_battery_saver'] is bool) 'os_battery_saver': battery!['os_battery_saver'],
        'battery_sample_at_ms': atMs,
        'previous_battery_sample_at_ms': previousMs,
        'previous_battery_level': previous?['level'],
        'previous_battery_charging': previous?['charging'],
        'previous_battery_observation_build': previous?['build'],
        'battery_interval_seconds': elapsedMs != null && elapsedMs > 0 ? elapsedMs / 1000.0 : null,
        'battery_interval_validity': validity,
        'battery_observation_build': build,
        'foreground_seconds_in_interval': foregroundSeconds,
        'app_lifecycle': lifecycle,
        'capture_source': capture.source,
        'capture_mode': capture.mode,
        'seconds_since_build_first_run': buildAge,
        'thermal_state': _thermalState(battery?['thermal_state']),
        'charging_observed_in_interval': chargingObserved ? true : null,
      });
      _previous = identity == null ? null : next;
      _identityChanged = false;
      // Retain lifecycle/callback observations arriving while persistence awaits.
      _foregroundMs -= foregroundMsAtSample;
      _intervalClockInvalid = _clockInvalidGeneration != clockGenerationAtSample;
      _foregroundCoverage = true;
      if (_chargingObservedAtMs != null && _chargingObservedAtMs! <= atMs) _chargingObservedAtMs = null;
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
      _identityChanges.removeListener(_onIdentityChanged);
    }
  }
}
