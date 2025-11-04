import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/http/api/device.dart';
import 'package:omi/main.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/confirmation_dialog.dart';

class DeviceProvider extends ChangeNotifier implements IDeviceServiceSubsciption {
  CaptureProvider? captureProvider;

  bool isConnecting = false;
  bool isConnected = false;
  bool isDeviceStorageSupport = false;
  BtDevice? connectedDevice;
  BtDevice? pairedDevice;
  StreamSubscription<List<int>>? _bleBatteryLevelListener;
  int batteryLevel = -1;
  bool _hasLowBatteryAlerted = false;
  Timer? _reconnectionTimer;
  DateTime? _reconnectAt;
  final int _connectionCheckSeconds = 15; // 10s periods, 5s for each scan

  bool _havingNewFirmware = false;
  bool get havingNewFirmware => _havingNewFirmware && pairedDevice != null && isConnected;

  // Track firmware update state to prevent showing dialog during updates
  bool _isFirmwareUpdateInProgress = false;
  bool get isFirmwareUpdateInProgress => _isFirmwareUpdateInProgress;

  // Current and latest firmware versions for UI display
  String get currentFirmwareVersion => pairedDevice?.firmwareRevision ?? 'Unknown';
  String _latestFirmwareVersion = '';
  String get latestFirmwareVersion => _latestFirmwareVersion;

  Timer? _disconnectNotificationTimer;
  final Debouncer _disconnectDebouncer = Debouncer(delay: const Duration(milliseconds: 500));
  final Debouncer _connectDebouncer = Debouncer(delay: const Duration(milliseconds: 100));

  // Battery handling state
  bool _awaitingFreshBattery = false;
  bool get isAwaitingFreshBattery => _awaitingFreshBattery;
  bool get hasBatteryReading => !_awaitingFreshBattery && batteryLevel >= 0;
  int? get lastKnownBatteryLevel => batteryLevel >= 0 ? batteryLevel : _lastPersistedBattery;

  int? _lastPersistedBattery;
  DateTime? _batteryLastUpdatedAt;
  DateTime? _previousBatteryTimestamp;
  int? _baselineBeforeReconnect;
  DateTime? _riseWindowStart;
  int? _riseWindowMinValue;
  int? _riseWindowMaxValue;
  int? _riseWindowLastSample;
  int _riseWindowDistinctSteps = 0;
  bool _isPrimingBattery = false;
  Timer? _batteryPrimeRetryTimer;

  static const int _riseIncreaseThreshold = 5;
  static const int _firstRiseCap = 10;
  static const int _requiredRiseSteps = 2;
  static const int _riseStepMinimumDelta = 1;
  static const Duration _baselineStaleThreshold = Duration(hours: 6);
  static const double _riseWindowEmaAlpha = 0.3;
  int _riseWindowMs = 45000;

  // Non-charging rise suppression and stabilization
  static const Duration _noRiseSuppressDuration = Duration(seconds: 45);
  static const int _nonChargingRiseSoftCap = 2;
  static const Duration _nonChargingStableWindow = Duration(minutes: 3);
  static const Duration _earlyAttachWindow = Duration(seconds: 12);
  static const int _earlyAttachNeededSamples = 3;
  DateTime? _noRiseUntil;
  DateTime? _ncStableStart;
  int? _ncStableMin;
  int? _ncStableMax;
  DateTime _appStartedAt = DateTime.now();
  final List<int> _earlyAttachSamples = [];

  // Telemetry and charging detection
  static const int _metricsLogEvery = 12;
  static const int _chargingRiseMinSamples = 2;
  static const int _chargingRiseMinDelta = 3;
  static const Duration _chargingObservationWindow = Duration(minutes: 2);
  static const int _chargingLargeJumpThreshold = 4;
  static const int _defaultStableStreakThreshold = 20;
  DateTime? _lastBatteryEventAt;
  int _batteryEventCount = 0;
  double _batteryIntervalSumMs = 0;
  int? _lastRawSample;
  int _sameValueStreak = 0;
  int _maxSameValueStreak = 0;
  final List<int> _recentStreakLengths = [];
  static const int _recentStreakWindow = 10;
  int _chargingRiseSamples = 0;
  int _chargingRiseDelta = 0;
  DateTime? _chargingWindowStart;
  int? _chargingLastRaw;
  bool _chargingLikely = false;

  DeviceProvider() {
    _appStartedAt = DateTime.now();
    ServiceManager.instance().device.subscribe(this, this);
  }

  void setProviders(CaptureProvider provider) {
    captureProvider = provider;
    notifyListeners();
  }

  void setConnectedDevice(BtDevice? device) async {
    connectedDevice = device;
    pairedDevice = device;

    if (connectedDevice != null) {
      final id = connectedDevice!.id;
      final cached = SharedPreferencesUtil().getLastBatteryLevel(id);
      final ts = SharedPreferencesUtil().getLastBatteryTimestamp(id);
      _lastPersistedBattery = cached;
      _batteryLastUpdatedAt = ts;
      _previousBatteryTimestamp = ts;
      _baselineBeforeReconnect = cached;
      final storedWindow = SharedPreferencesUtil().getInt('batteryRiseWindow:$id');
      if (storedWindow != null) {
        _riseWindowMs = storedWindow.clamp(20000, 90000);
      } else {
        _riseWindowMs = 45000;
      }

      if (cached != null && cached >= 0) {
        batteryLevel = cached;
      } else {
        batteryLevel = -1;
      }

      _awaitingFreshBattery = true;
      notifyListeners();

      // Initialize non-charging suppression window and stabilization trackers
      final now = DateTime.now();
      _noRiseUntil = now.add(_noRiseSuppressDuration);
      _ncStableStart = null;
      _ncStableMin = null;
      _ncStableMax = null;
      _earlyAttachSamples.clear();

      await initiateBleBatteryListener();
      _primeBatteryLevel();
    } else {
      _awaitingFreshBattery = false;
      _baselineBeforeReconnect = null;
      _noRiseUntil = null;
      _ncStableStart = null;
      _ncStableMin = null;
      _ncStableMax = null;
      _earlyAttachSamples.clear();
      _lastRawSample = null;
      _sameValueStreak = 0;
      _maxSameValueStreak = 0;
      _recentStreakLengths.clear();
      _batteryEventCount = 0;
      _batteryIntervalSumMs = 0;
      _lastBatteryEventAt = null;
      _batteryPrimeRetryTimer?.cancel();
      _batteryPrimeRetryTimer = null;
      _isPrimingBattery = false;
    }

    await getDeviceInfo();
    Logger.debug('setConnectedDevice: $device');
    notifyListeners();
  }

  Future getDeviceInfo() async {
    if (connectedDevice != null) {
      if (pairedDevice?.firmwareRevision != null && pairedDevice?.firmwareRevision != 'Unknown') {
        return;
      }
      var connection = await ServiceManager.instance().device.ensureConnection(connectedDevice!.id);
      pairedDevice = await connectedDevice?.getDeviceInfo(connection);
      SharedPreferencesUtil().btDevice = pairedDevice!;
    } else {
      if (SharedPreferencesUtil().btDevice.id.isEmpty) {
        pairedDevice = BtDevice.empty();
      } else {
        pairedDevice = SharedPreferencesUtil().btDevice;
      }
    }
    notifyListeners();
  }

  // TODO: thinh, use connection directly
  Future _bleDisconnectDevice(BtDevice btDevice) async {
    var connection = await ServiceManager.instance().device.ensureConnection(btDevice.id);
    if (connection == null) {
      return Future.value(null);
    }
    return await connection.disconnect();
  }

  Future<StreamSubscription<List<int>>?> _getBleBatteryLevelListener(
    String deviceId, {
    void Function(int)? onBatteryLevelChange,
  }) async {
    {
      var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
      if (connection == null) {
        return Future.value(null);
      }
      return connection.getBleBatteryLevelListener(onBatteryLevelChange: onBatteryLevelChange);
    }
  }

  Future<List<int>> _getStorageList(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return [];
    }
    return connection.getStorageList();
  }

  Future<BtDevice?> _getConnectedDevice() async {
    var deviceId = SharedPreferencesUtil().btDevice.id;
    if (deviceId.isEmpty) {
      return null;
    }
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    return connection?.device;
  }

  initiateBleBatteryListener() async {
    if (connectedDevice == null) {
      return;
    }
    _bleBatteryLevelListener?.cancel();
    _bleBatteryLevelListener = await _getBleBatteryLevelListener(
      connectedDevice!.id,
      onBatteryLevelChange: (int value) {
        _handleIncomingBatteryValue(value);
        if (batteryLevel >= 0 && batteryLevel < 20 && !_hasLowBatteryAlerted) {
          _hasLowBatteryAlerted = true;
          NotificationService.instance.createNotification(
            title: "Low Battery Alert",
            body: "Your device is running low on battery. Time for a recharge! 🔋",
          );
        } else if (batteryLevel >= 20) {
          _hasLowBatteryAlerted = false;
        }
      },
    );
    notifyListeners();
  }

  void _persistBatteryLevel(int level, DateTime timestamp) {
    final id = connectedDevice?.id ?? SharedPreferencesUtil().btDevice.id;
    if (id.isEmpty) return;
    _lastPersistedBattery = level;
    _batteryLastUpdatedAt = timestamp;
    _previousBatteryTimestamp = timestamp;
    SharedPreferencesUtil().saveLastBatteryLevel(id, level, timestamp);
  }

  void _recordBatteryMetrics(int rawValue, DateTime now) {
    if (_lastBatteryEventAt != null) {
      _batteryIntervalSumMs += now.difference(_lastBatteryEventAt!).inMilliseconds;
    }
    _batteryEventCount++;

    if (_lastRawSample != null && rawValue == _lastRawSample) {
      _sameValueStreak++;
    } else {
      if (_lastRawSample != null) {
        _recentStreakLengths.add(_sameValueStreak);
        if (_recentStreakLengths.length > _recentStreakWindow) {
          _recentStreakLengths.removeAt(0);
        }
        Logger.debug(
            'Battery repetition: value=$_lastRawSample count=$_sameValueStreak avg=${_calculateAverageStreak().toStringAsFixed(1)}');
      }
      _sameValueStreak = 1;
    }
    if (_sameValueStreak > _maxSameValueStreak) {
      _maxSameValueStreak = _sameValueStreak;
    }

    _lastRawSample = rawValue;
    _lastBatteryEventAt = now;

    assert(() {
      Logger.debug(
          'Battery sample $_batteryEventCount value=$rawValue streak=$_sameValueStreak baseline=${_baselineBeforeReconnect ?? _lastPersistedBattery}');
      return true;
    }());

    if (_batteryEventCount % _metricsLogEvery == 0) {
      final avgSeconds = _batteryEventCount <= 1 ? 0 : (_batteryIntervalSumMs / (_batteryEventCount - 1)) / 1000;
      Logger.debug(
          'Battery cadence: events=$_batteryEventCount avg=${avgSeconds.toStringAsFixed(1)}s maxStreak=$_maxSameValueStreak');
    }
  }

  void _resetChargingMonitor() {
    _chargingRiseSamples = 0;
    _chargingRiseDelta = 0;
    _chargingWindowStart = null;
    _chargingLastRaw = null;
    _chargingLikely = false;
  }

  double _calculateAverageStreak() {
    if (_recentStreakLengths.isEmpty) {
      return _defaultStableStreakThreshold.toDouble();
    }
    final total = _recentStreakLengths.fold<int>(0, (sum, value) => sum + value);
    return total / _recentStreakLengths.length;
  }

  int _requiredStableStreakLength() {
    final average = _calculateAverageStreak();
    return math.max(5, average.ceil());
  }

  void _updateChargingMonitor(int rawValue, int baseline, DateTime now) {
    if (rawValue <= baseline) {
      _resetChargingMonitor();
      return;
    }

    if (_chargingLastRaw != null && rawValue < _chargingLastRaw!) {
      _resetChargingMonitor();
    }

    if (_chargingRiseSamples == 0) {
      _chargingWindowStart = now;
      _chargingRiseDelta = rawValue - baseline;
      _chargingRiseSamples = 1;
    } else {
      _chargingRiseDelta += rawValue - (_chargingLastRaw ?? rawValue);
      _chargingRiseSamples++;
    }

    final window = _chargingWindowStart == null ? Duration.zero : now.difference(_chargingWindowStart!);
    final riseDelta = rawValue - baseline;
    if (!_chargingLikely &&
        _chargingRiseSamples >= _chargingRiseMinSamples &&
        riseDelta >= _chargingRiseMinDelta &&
        window <= _chargingObservationWindow) {
      _chargingLikely = true;
      assert(() {
        Logger.debug(
            'Charging likely: baseline=$baseline raw=$rawValue samples=$_chargingRiseSamples delta=$riseDelta window=${window.inSeconds}s');
        return true;
      }());
    }

    _chargingLastRaw = rawValue;
  }

  bool _shouldAcceptStableRise(int rawValue, int baseline) {
    if (rawValue <= baseline) {
      return false;
    }
    if (_sameValueStreak < 3) {
      return false;
    }

    final threshold = _requiredStableStreakLength();
    if (_sameValueStreak < threshold) {
      return false;
    }

    // Guard against unrealistically high jumps.
    if (rawValue > baseline + _firstRiseCap) {
      return false;
    }

    return true;
  }

  bool _handleIncomingBatteryValue(int rawValue, {DateTime? timestamp}) {
    if (rawValue < 0 || rawValue > 100) {
      return false;
    }

    final now = timestamp ?? DateTime.now();
    _recordBatteryMetrics(rawValue, now);
    final baselineCandidate = _baselineBeforeReconnect ?? _lastPersistedBattery;
    final hasBaseline = baselineCandidate != null;
    final displayReference = batteryLevel >= 0 ? batteryLevel : (_lastPersistedBattery ?? rawValue);
    final jumpFromDisplayInitial = displayReference >= 0 ? rawValue - displayReference : 0;
    final isLargeJump = jumpFromDisplayInitial >= _chargingLargeJumpThreshold;
    final attachElapsed = now.difference(_appStartedAt);

    // First ever reading: accept immediately
    if (_riseWindowStart == null && !hasBaseline && _lastPersistedBattery == null) {
      return _finalizeAndApply(rawValue, now);
    }

    if (hasBaseline) {
      final baselineAge = _batteryLastUpdatedAt == null ? Duration.zero : now.difference(_batteryLastUpdatedAt!);
      final baselineStale = baselineAge > _baselineStaleThreshold;

      if (rawValue > baselineCandidate!) {
        _updateChargingMonitor(rawValue, baselineCandidate, now);
      }

      if (!baselineStale && rawValue > baselineCandidate + _riseIncreaseThreshold) {
        final allowEarlyAttach = _awaitingFreshBattery && attachElapsed <= _earlyAttachWindow;
        final allowChargingSpike = _chargingLikely || isLargeJump;
        if (!allowEarlyAttach && !allowChargingSpike) {
          if (!_isPrimingBattery) {
            _primeBatteryLevel();
          }
          return false;
        }
      }
    }

    if (!_awaitingFreshBattery) {
      // Ongoing mode: conservative acceptance when not charging.
      final display = displayReference;
      final baseline = _baselineBeforeReconnect ?? _lastPersistedBattery ?? display;

      int nextValue;
      if (rawValue <= display) {
        // Immediate drops are accepted; allow baseline to move down only.
        nextValue = rawValue;
        _ncStableStart = null;
        _ncStableMin = null;
        _ncStableMax = null;
        if (_earlyAttachSamples.isNotEmpty) {
          _earlyAttachSamples.clear();
        }
        _resetChargingMonitor();
      } else if (attachElapsed <= _earlyAttachWindow) {
        _earlyAttachSamples.add(rawValue);
        if (_earlyAttachSamples.length > 5) {
          _earlyAttachSamples.removeAt(0);
        }
        final minSample = _earlyAttachSamples.reduce(math.min);
        final maxSample = _earlyAttachSamples.reduce(math.max);
        final stable = _earlyAttachSamples.length >= _earlyAttachNeededSamples && (maxSample - minSample) <= 1;
        if (stable) {
          nextValue = math.min(rawValue, baseline + _firstRiseCap);
          _noRiseUntil = null;
          _ncStableStart = null;
          _ncStableMin = null;
          _ncStableMax = null;
          _earlyAttachSamples.clear();
          _resetChargingMonitor();
        } else {
          return false;
        }
      } else if (rawValue > baseline) {
        if (_earlyAttachSamples.isNotEmpty) {
          _earlyAttachSamples.clear();
        }
        final jumpFromDisplay = rawValue - display;
        _updateChargingMonitor(rawValue, baseline, now);

        if (_chargingLikely && jumpFromDisplay >= _chargingLargeJumpThreshold && rawValue <= baseline + _firstRiseCap) {
          nextValue = math.min(rawValue, baseline + _firstRiseCap);
          _noRiseUntil = null;
          _ncStableStart = null;
          _ncStableMin = null;
          _ncStableMax = null;
          _resetChargingMonitor();
        } else if (_shouldAcceptStableRise(rawValue, baseline)) {
          nextValue = math.min(rawValue, baseline + _firstRiseCap);
          _ncStableStart = null;
          _ncStableMin = null;
          _ncStableMax = null;
          _resetChargingMonitor();
        } else {
          if (_noRiseUntil != null && now.isBefore(_noRiseUntil!)) {
            return false;
          }

          if (rawValue <= baseline + _nonChargingRiseSoftCap) {
            nextValue = rawValue;
            _ncStableStart = null;
            _ncStableMin = null;
            _ncStableMax = null;
            _resetChargingMonitor();
          } else {
            if (_chargingLikely && rawValue <= baseline + _firstRiseCap) {
              nextValue = math.min(rawValue, baseline + _firstRiseCap);
              _ncStableStart = null;
              _ncStableMin = null;
              _ncStableMax = null;
              _resetChargingMonitor();
            } else if (_chargingLikely) {
              return false;
            } else if (_ncStableStart == null) {
              _ncStableStart = now;
              _ncStableMin = rawValue;
              _ncStableMax = rawValue;
              return false;
            } else {
              _ncStableMin = (_ncStableMin == null) ? rawValue : math.min(_ncStableMin!, rawValue);
              _ncStableMax = (_ncStableMax == null) ? rawValue : math.max(_ncStableMax!, rawValue);
              final elapsed = now.difference(_ncStableStart!);
              final jitter = (_ncStableMax! - _ncStableMin!).abs();
              if (elapsed >= _nonChargingStableWindow && jitter <= 1) {
                nextValue = math.min(rawValue, baseline + _firstRiseCap);
                _ncStableStart = null;
                _ncStableMin = null;
                _ncStableMax = null;
                _resetChargingMonitor();
              } else {
                return false;
              }
            }
          }
        }
      } else {
        // rawValue <= baseline but greater than display; accept but clamp naturally by value.
        nextValue = rawValue;
        _ncStableStart = null;
        _ncStableMin = null;
        _ncStableMax = null;
        if (_earlyAttachSamples.isNotEmpty) {
          _earlyAttachSamples.clear();
        }
        _resetChargingMonitor();
      }

      if (batteryLevel != nextValue) {
        batteryLevel = nextValue;
        _persistBatteryLevel(nextValue, now);
        notifyListeners();
      } else {
        _persistBatteryLevel(nextValue, now);
      }

      // Baseline: only decrease; allow promotion when we deliberately accept a stabilized rise or confirmed charging jump.
      final jumpFromDisplayFinal = nextValue - display;
      final acceptedChargingRise =
          nextValue > baseline && (_chargingLikely || jumpFromDisplayFinal >= _chargingLargeJumpThreshold);
      if (_baselineBeforeReconnect == null || nextValue <= _baselineBeforeReconnect!) {
        _baselineBeforeReconnect = nextValue;
      } else if (attachElapsed <= _earlyAttachWindow || acceptedChargingRise) {
        _baselineBeforeReconnect = nextValue;
      }
      return true;
    }

    if (_awaitingFreshBattery) {
      if (baselineCandidate != null && attachElapsed <= _earlyAttachWindow && rawValue > baselineCandidate) {
        _earlyAttachSamples.add(rawValue);
        if (_earlyAttachSamples.length > 5) {
          _earlyAttachSamples.removeAt(0);
        }
        final minSample = _earlyAttachSamples.reduce(math.min);
        final maxSample = _earlyAttachSamples.reduce(math.max);
        final stable = _earlyAttachSamples.length >= _earlyAttachNeededSamples && (maxSample - minSample) <= 1;
        if (stable) {
          _noRiseUntil = null;
          _ncStableStart = null;
          _ncStableMin = null;
          _ncStableMax = null;
          _resetChargingMonitor();
          return _finalizeAndApply(rawValue, now);
        }
        return false;
      }
    }

    if (_riseWindowStart == null) {
      _riseWindowStart = now;
      _riseWindowMinValue = rawValue;
      _riseWindowMaxValue = rawValue;
      _riseWindowLastSample = rawValue;
      _riseWindowDistinctSteps = 0;
    } else {
      _riseWindowMinValue = _riseWindowMinValue == null ? rawValue : math.min(_riseWindowMinValue!, rawValue);
      _riseWindowMaxValue = _riseWindowMaxValue == null ? rawValue : math.max(_riseWindowMaxValue!, rawValue);
      if (_riseWindowLastSample != null && rawValue > _riseWindowLastSample!) {
        if (rawValue - _riseWindowLastSample! >= _riseStepMinimumDelta) {
          _riseWindowDistinctSteps++;
        }
      }
      _riseWindowLastSample = rawValue;
    }

    if (baselineCandidate != null && rawValue <= baselineCandidate) {
      return _finalizeAndApply(rawValue, now);
    }

    if (baselineCandidate != null) {
      final elapsedMs = now.difference(_riseWindowStart!).inMilliseconds;
      final minVal = _riseWindowMinValue ?? rawValue;
      final maxVal = _riseWindowMaxValue ?? rawValue;
      final sustainedRise = minVal >= baselineCandidate + _riseIncreaseThreshold;
      final sawRamp = _riseWindowDistinctSteps >= _requiredRiseSteps;
      final plateauSpan = (maxVal - minVal).abs();
      final stableRise = sustainedRise && plateauSpan <= 1 && elapsedMs >= _riseWindowMs;
      final timedOut = elapsedMs >= _riseWindowMs && minVal >= baselineCandidate;
      if ((sustainedRise && sawRamp && elapsedMs >= _riseWindowMs) || stableRise || timedOut) {
        _updateRiseWindow(elapsedMs);
        final candidate = math.min(minVal, rawValue);
        final capped = math.min(candidate, baselineCandidate + _firstRiseCap);
        return _finalizeAndApply(capped, now);
      }
    } else {
      final elapsedMs = now.difference(_riseWindowStart!).inMilliseconds;
      final minVal = _riseWindowMinValue ?? rawValue;
      final maxVal = _riseWindowMaxValue ?? rawValue;
      if (elapsedMs >= _riseWindowMs && (maxVal - minVal).abs() <= _riseIncreaseThreshold) {
        return _finalizeAndApply(minVal, now);
      }
    }

    if (!_isPrimingBattery) {
      _primeBatteryLevel();
    }
    return false;
  }

  bool _finalizeAndApply(int acceptedValue, DateTime timestamp) {
    _awaitingFreshBattery = false;
    _baselineBeforeReconnect = acceptedValue;
    _riseWindowStart = null;
    _riseWindowMinValue = null;
    _riseWindowMaxValue = null;
    _riseWindowLastSample = null;
    _riseWindowDistinctSteps = 0;
    if (_earlyAttachSamples.isNotEmpty) {
      _earlyAttachSamples.clear();
    }
    _resetChargingMonitor();
    _lastRawSample = acceptedValue;
    _sameValueStreak = 1;
    _maxSameValueStreak = math.max(_maxSameValueStreak, 1);

    if (batteryLevel != acceptedValue) {
      batteryLevel = acceptedValue;
      _persistBatteryLevel(acceptedValue, timestamp);
      notifyListeners();
    } else {
      _persistBatteryLevel(acceptedValue, timestamp);
    }
    return true;
  }

  void _updateRiseWindow(int elapsedMs) {
    if (elapsedMs <= 0) return;
    final id = connectedDevice?.id ?? SharedPreferencesUtil().btDevice.id;
    if (id.isEmpty) return;
    final updated = ((_riseWindowMs * (1 - _riseWindowEmaAlpha)) + (elapsedMs * _riseWindowEmaAlpha)).round();
    _riseWindowMs = updated.clamp(20000, 90000);
    SharedPreferencesUtil().saveInt('batteryRiseWindow:$id', _riseWindowMs);
  }

  Future<void> _primeBatteryLevel() async {
    if (connectedDevice == null || _isPrimingBattery) {
      return;
    }
    _isPrimingBattery = true;
    _batteryPrimeRetryTimer?.cancel();

    const delays = <Duration>[
      Duration(milliseconds: 0),
      Duration(milliseconds: 200),
      Duration(milliseconds: 600),
      Duration(milliseconds: 1200),
      Duration(milliseconds: 3000),
      Duration(milliseconds: 6000),
      Duration(milliseconds: 9000),
      Duration(milliseconds: 12000),
      Duration(milliseconds: 15000),
    ];

    try {
      final connection = await ServiceManager.instance().device.ensureConnection(connectedDevice!.id);
      if (connection == null) {
        return;
      }
      for (final delay in delays) {
        if (delay.inMilliseconds > 0) {
          await Future.delayed(delay);
        }
        try {
          final level = await connection.retrieveBatteryLevel();
          if (level >= 0 && level <= 100) {
            final accepted = _handleIncomingBatteryValue(level);
            if (accepted) {
              return;
            }
          }
        } catch (_) {}
      }
    } finally {
      _isPrimingBattery = false;
    }

    if (_awaitingFreshBattery) {
      _batteryPrimeRetryTimer = Timer(const Duration(seconds: 1), () {
        if (connectedDevice != null && _awaitingFreshBattery) {
          _primeBatteryLevel();
        }
      });
    }
  }

  Future periodicConnect(String printer, {bool boundDeviceOnly = false}) async {
    _reconnectionTimer?.cancel();
    scan(t) async {
      debugPrint("Period connect seconds: $_connectionCheckSeconds, triggered timer at ${DateTime.now()}");
      if (_reconnectAt != null && _reconnectAt!.isAfter(DateTime.now())) {
        return;
      }
      if (boundDeviceOnly && SharedPreferencesUtil().btDevice.id.isEmpty) {
        t.cancel();
        return;
      }
      Logger.debug("isConnected: $isConnected, isConnecting: $isConnecting, connectedDevice: $connectedDevice");
      if ((!isConnected && connectedDevice == null)) {
        if (isConnecting) {
          return;
        }
        await scanAndConnectToDevice();
      } else {
        t.cancel();
      }
    }

    _reconnectionTimer = Timer.periodic(Duration(seconds: _connectionCheckSeconds), scan);
    scan(_reconnectionTimer);
  }

  Future<BtDevice?> _scanConnectDevice() async {
    var device = await _getConnectedDevice();
    if (device != null) {
      return device;
    }

    final pairedDeviceId = SharedPreferencesUtil().btDevice.id;
    if (pairedDeviceId.isNotEmpty) {
      try {
        Logger.debug('Attempting direct reconnection to paired device: $pairedDeviceId');
        await ServiceManager.instance().device.ensureConnection(pairedDeviceId, force: true);

        // Check if connection succeeded
        await Future.delayed(const Duration(seconds: 2));
        device = await _getConnectedDevice();
        if (device != null) {
          Logger.debug('Direct reconnection successful');
          return device;
        }
      } catch (e) {
        Logger.debug('Direct reconnection failed: $e');
      }
    }

    await ServiceManager.instance().device.discover(desirableDeviceId: pairedDeviceId);

    // Waiting for the device connected (if any)
    await Future.delayed(const Duration(seconds: 2));
    if (connectedDevice != null) {
      return connectedDevice;
    }
    return null;
  }

  Future scanAndConnectToDevice() async {
    updateConnectingStatus(true);
    if (isConnected) {
      if (connectedDevice == null) {
        connectedDevice = await _getConnectedDevice();
        SharedPreferencesUtil().deviceName = connectedDevice!.name;
        MixpanelManager().deviceConnected();
      }

      setIsConnected(true);
      updateConnectingStatus(false);
      notifyListeners();
      return;
    }

    // else
    var device = await _scanConnectDevice();
    Logger.debug('inside scanAndConnectToDevice $device in device_provider');
    if (device != null) {
      var cDevice = await _getConnectedDevice();
      if (cDevice != null) {
        setConnectedDevice(cDevice);
        setisDeviceStorageSupport();
        SharedPreferencesUtil().deviceName = cDevice.name;
        MixpanelManager().deviceConnected();
        setIsConnected(true);
      }
      Logger.debug('device is not null $cDevice');
    }
    updateConnectingStatus(false);

    notifyListeners();
  }

  void updateConnectingStatus(bool value) {
    isConnecting = value;
    notifyListeners();
  }

  void setIsConnected(bool value) {
    isConnected = value;
    if (isConnected) {
      _reconnectionTimer?.cancel();
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _bleBatteryLevelListener?.cancel();
    _reconnectionTimer?.cancel();
    _batteryPrimeRetryTimer?.cancel();
    _isPrimingBattery = false;
    _disconnectDebouncer.cancel();
    _connectDebouncer.cancel();
    ServiceManager.instance().device.unsubscribe(this);
    super.dispose();
  }

  void onDeviceDisconnected() async {
    Logger.debug('onDisconnected inside: $connectedDevice');
    _havingNewFirmware = false;
    setConnectedDevice(null);
    setisDeviceStorageSupport();
    setIsConnected(false);
    updateConnectingStatus(false);

    captureProvider?.updateRecordingDevice(null);

    // Wals
    ServiceManager.instance().wal.getSyncs().sdcard.setDevice(null);

    PlatformManager.instance.crashReporter.logInfo('Omi Device Disconnected');
    _disconnectNotificationTimer?.cancel();
    _disconnectNotificationTimer = Timer(const Duration(seconds: 30), () {
      NotificationService.instance.createNotification(
        title: 'Your Omi Device Disconnected',
        body: 'Please reconnect to continue using your Omi.',
      );
    });
    MixpanelManager().deviceDisconnected();

    // Retired 1s to prevent the race condition made by standby power of ble device
    Future.delayed(const Duration(seconds: 1), () {
      periodicConnect('coming from onDisconnect');
    });
  }

  Future<(String, bool, String)> shouldUpdateFirmware() async {
    if (pairedDevice == null || connectedDevice == null) {
      return ('No paired device is connected', false, '');
    }

    var device = pairedDevice!;
    var latestFirmwareDetails = await getLatestFirmwareVersion(
      deviceModelNumber: device.modelNumber,
      firmwareRevision: device.firmwareRevision,
      hardwareRevision: device.hardwareRevision,
      manufacturerName: device.manufacturerName,
    );

    return await DeviceUtils.shouldUpdateFirmware(
        currentFirmware: device.firmwareRevision, latestFirmwareDetails: latestFirmwareDetails);
  }

  void _onDeviceConnected(BtDevice device) async {
    Logger.debug('_onConnected inside: $connectedDevice');
    _disconnectNotificationTimer?.cancel();
    NotificationService.instance.clearNotification(1);
    setConnectedDevice(device);

    if (captureProvider != null) {
      captureProvider?.updateRecordingDevice(device);
    }

    setisDeviceStorageSupport();
    setIsConnected(true);

    await initiateBleBatteryListener();
    if (batteryLevel != -1 && batteryLevel < 20) {
      _hasLowBatteryAlerted = false;
    }
    updateConnectingStatus(false);
    await captureProvider?.streamDeviceRecording(device: device);

    await getDeviceInfo();
    SharedPreferencesUtil().deviceName = device.name;

    // Wals
    ServiceManager.instance().wal.getSyncs().sdcard.setDevice(device);

    notifyListeners();

    // Check firmware updates
    _checkFirmwareUpdates();
  }

  void _handleDeviceConnected(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return;
    }
    _onDeviceConnected(connection.device);
  }

  void _checkFirmwareUpdates() async {
    if (_isFirmwareUpdateInProgress) {
      return;
    }

    await checkFirmwareUpdates();

    // Show firmware update dialog if needed
    if (_havingNewFirmware) {
      // Use a small delay to ensure the UI is ready
      Future.delayed(const Duration(milliseconds: 500), () {
        final context = MyApp.navigatorKey.currentContext;
        if (context != null) {
          showFirmwareUpdateDialog(context);
        }
      });
    }
  }

  Future checkFirmwareUpdates() async {
    int retryCount = 0;
    const maxRetries = 3;
    const retryDelay = Duration(seconds: 3);

    while (retryCount < maxRetries) {
      try {
        var (message, hasUpdate, version) = await shouldUpdateFirmware();
        _havingNewFirmware = hasUpdate;
        _latestFirmwareVersion = version.isNotEmpty ? version : message;
        notifyListeners();
        return hasUpdate; // Return whether there's an update
      } catch (e) {
        retryCount++;
        Logger.debug('Error checking firmware update (attempt $retryCount): $e');

        if (retryCount == maxRetries) {
          Logger.debug('Max retries reached, giving up');
          _havingNewFirmware = false;
          notifyListeners();
          break;
        }

        await Future.delayed(retryDelay);
      }
    }
    return;
  }

  void showFirmwareUpdateDialog(BuildContext context) {
    if (!_havingNewFirmware || !SharedPreferencesUtil().showFirmwareUpdateDialog || _isFirmwareUpdateInProgress) {
      return;
    }

    showDialog(
      context: context,
      builder: (context) => ConfirmationDialog(
        title: 'Firmware Update Available',
        description:
            'A new firmware update ($_latestFirmwareVersion) is available for your Omi device. Would you like to update now?',
        confirmText: 'Update',
        cancelText: 'Later',
        onConfirm: () {
          Navigator.of(context).pop();
          setFirmwareUpdateInProgress(true);
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (context) => FirmwareUpdate(device: pairedDevice),
            ),
          );
        },
        onCancel: () {
          Navigator.of(context).pop();
        },
      ),
    );
  }

  Future setisDeviceStorageSupport() async {
    if (connectedDevice == null) {
      isDeviceStorageSupport = false;
    } else {
      var storageFiles = await _getStorageList(connectedDevice!.id);
      isDeviceStorageSupport = storageFiles.isNotEmpty;
    }
    notifyListeners();
  }

  @override
  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) async {
    Logger.debug("provider > device connection state changed...$deviceId...$state...${connectedDevice?.id}");
    switch (state) {
      case DeviceConnectionState.connected:
        _disconnectDebouncer.cancel();
        _connectDebouncer.run(() => _handleDeviceConnected(deviceId));
        break;
      case DeviceConnectionState.disconnected:
        _connectDebouncer.cancel();
        // Check if this is the paired device or currently connected device
        // Coz connectedDevice and pairedDevice are the same but connectedDevice becomes null after disconnect
        if (deviceId == connectedDevice?.id || deviceId == pairedDevice?.id) {
          _disconnectDebouncer.run(onDeviceDisconnected);
        }
        break;
      default:
        Logger.debug("Device connection state is not supported $state");
    }
  }

  @override
  void onDevices(List<BtDevice> devices) async {}

  @override
  void onStatusChanged(DeviceServiceStatus status) {}

  prepareDFU() {
    if (connectedDevice == null) {
      return;
    }
    _bleDisconnectDevice(connectedDevice!);
    _reconnectAt = DateTime.now().add(Duration(seconds: 30));
  }

  // Reset firmware update state when update completes or fails
  void resetFirmwareUpdateState() {
    _isFirmwareUpdateInProgress = false;
    notifyListeners();
  }

  // Set firmware update state when starting an update
  void setFirmwareUpdateInProgress(bool inProgress) {
    _isFirmwareUpdateInProgress = inProgress;
    notifyListeners();
  }
}
