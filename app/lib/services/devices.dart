import 'dart:async';

import 'package:collection/collection.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/discovery/apple_watch_discoverer.dart';
import 'package:omi/services/devices/discovery/rayban_meta_discoverer.dart';
import 'package:omi/services/devices/discovery/device_discoverer.dart';
import 'package:omi/services/devices/discovery/native_bluetooth_discoverer.dart';
import 'package:omi/services/devices/errors.dart';
import 'package:omi/utils/ble_connect_retry.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/mutex.dart';

enum DeviceServiceStatus { init, ready, scanning, stop }

enum DeviceConnectionState { connected, connecting, disconnected }

/// Feature flags for Omi device capabilities
/// Must match the firmware definitions in features.h
class OmiFeatures {
  static const int speaker = 1 << 0;
  static const int accelerometer = 1 << 1;
  static const int button = 1 << 2;
  static const int battery = 1 << 3;
  static const int usb = 1 << 4;
  static const int haptic = 1 << 5;
  static const int offlineStorage = 1 << 6;
  static const int ledDimming = 1 << 7;
  static const int micGain = 1 << 8;
}

abstract class IDeviceServiceSubsciption {
  void onDevices(List<BtDevice> devices);
  void onStatusChanged(DeviceServiceStatus status);
  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state);
}

class DeviceService {
  DeviceServiceStatus _status = DeviceServiceStatus.init;
  List<BtDevice> _devices = [];

  final List<DeviceDiscoverer> _discoverers = [
    NativeBluetoothDiscoverer(),
    AppleWatchDiscoverer(),
    RayBanMetaDiscoverer(),
  ];

  final Map<Object, IDeviceServiceSubsciption> _subscriptions = {};

  DeviceConnection? _connection;
  List<BtDevice> get devices => _devices;

  DeviceServiceStatus get status => _status;

  /// True after an explicit disconnect/forget until a successful connect.
  bool get suppressesAutoReconnect => _userDisconnectedBle;

  DateTime? _firstConnectedAt;

  // #6721 / #6610: after device-ready timeout / connect failure, soft-retry with
  // backoff without disposing the transport (native auto-reconnect must stay alive).
  Timer? _bleConnectRetryTimer;
  int _bleConnectRetryAttempt = 0;
  String? _bleConnectRetryDeviceId;
  bool _userDisconnectedBle = false;

  Future<void> discover({String? desirableDeviceId, int timeout = 5}) async {
    Logger.debug("Device discovering...");
    if (_status != DeviceServiceStatus.ready) {
      logCommonErrorMessage("Device service is not ready, may busying or stop");
      return;
    }

    _status = DeviceServiceStatus.scanning;

    try {
      final discoveredDevices = <BtDevice>[];

      final supportedDiscoverers = _discoverers.where((d) => d.isSupported).toList();
      final discoveryFutures = supportedDiscoverers.map((d) async {
        try {
          final result = await d.discover(timeout: timeout);
          return result.devices;
        } catch (e, st) {
          Logger.debug('Discovery failed for ${d.name}: $e');
          Logger.debug('$st');
          return <BtDevice>[];
        }
      });

      // Wait for all discoveries to complete
      final results = await Future.wait(discoveryFutures);

      // Combine all discovered devices
      for (final devices in results) {
        discoveredDevices.addAll(devices);
      }

      _devices = discoveredDevices;
      onDevices(devices);

      if (desirableDeviceId != null && desirableDeviceId.isNotEmpty) {
        await ensureConnection(desirableDeviceId, force: true);
      }
    } finally {
      _status = DeviceServiceStatus.ready;
    }
  }

  Future<void> _connectToDevice(String id, {required bool softRetry}) async {
    final reuseExisting =
        softRetry &&
        shouldSoftRetryExistingConnection(existingDeviceId: _connection?.device.id, targetDeviceId: id, force: true);

    if (!reuseExisting) {
      // Clean up existing connection — disconnect if active, then dispose transport
      if (_connection != null) {
        if (_connection!.status == DeviceConnectionState.connected) {
          await _connection!.disconnect();
        }
        await _connection!.transport.dispose();
      }
      _connection = null;

      var device = _devices.firstWhereOrNull((f) => f.id == id);
      Logger.debug(
        '[DeviceService] device lookup result: ${device?.name ?? "NULL"} (locator: ${device?.locator?.kind})',
      );

      // If device not in discovered list, try to get it from SharedPreferences
      // This allows background reconnection without scanning
      if (device == null) {
        Logger.debug('[DeviceService] Device not in discovered list, checking stored device');
        device = _getStoredDevice(id);
        if (device != null) {
          Logger.debug('[DeviceService] Using stored device: ${device.name}');
          if (!_devices.any((d) => d.id == device!.id)) {
            _devices.add(device);
          }
        } else {
          Logger.debug('[DeviceService] No stored device available for $id, returning');
          return;
        }
      }

      _connection = DeviceConnectionFactory.create(device);
    } else {
      Logger.debug('[DeviceService] soft-retrying existing transport for $id');
    }

    if (_connection != null) {
      await _connection!.connect(onConnectionStateChanged: onDeviceConnectionStateChanged);
    } else {
      Logger.debug('[DeviceService] Failed to create device connection for $id');
    }
  }

  void _cancelBleConnectRetry() {
    _bleConnectRetryTimer?.cancel();
    _bleConnectRetryTimer = null;
    _bleConnectRetryDeviceId = null;
  }

  void _resetBleConnectRetryState() {
    _cancelBleConnectRetry();
    _bleConnectRetryAttempt = 0;
  }

  void _scheduleBleConnectRetry(String deviceId) {
    final pairedId = SharedPreferencesUtil().btDevice.id;
    final should = shouldScheduleBleConnectRetry(
      serviceReady: _status == DeviceServiceStatus.ready || _status == DeviceServiceStatus.scanning,
      hasPairedDevice: pairedId.isNotEmpty && pairedId == deviceId,
      userDisconnected: _userDisconnectedBle,
      alreadyConnected: _connection?.device.id == deviceId && _connection?.status == DeviceConnectionState.connected,
      retryAlreadyScheduled: _bleConnectRetryTimer?.isActive == true,
    );
    if (!should) return;

    final delay = nextBleConnectRetryDelay(_bleConnectRetryAttempt);
    _bleConnectRetryAttempt += 1;
    _bleConnectRetryDeviceId = deviceId;
    Logger.debug(
      '[DeviceService] scheduling BLE soft-retry #$_bleConnectRetryAttempt for $deviceId in ${delay.inSeconds}s',
    );
    _bleConnectRetryTimer?.cancel();
    _bleConnectRetryTimer = Timer(delay, () {
      _bleConnectRetryTimer = null;
      unawaited(ensureConnection(deviceId, force: true, softRetry: true));
    });
  }

  void subscribe(IDeviceServiceSubsciption subscription, Object context) {
    _subscriptions.remove(context.hashCode);
    _subscriptions.putIfAbsent(context.hashCode, () => subscription);

    // Retains
    subscription.onDevices(_devices);
    subscription.onStatusChanged(_status);
  }

  void unsubscribe(Object context) {
    _subscriptions.remove(context.hashCode);
  }

  void start() {
    _status = DeviceServiceStatus.ready;
    // Auto-reconnect after connect/device-ready failures is handled by
    // _scheduleBleConnectRetry (#6610). Native owns in-session BLE reconnect.
  }

  void stop() {
    _userDisconnectedBle = true;
    _resetBleConnectRetryState();
    _status = DeviceServiceStatus.stop;
    onStatusChanged(_status);

    // Stop all discoverers to prevent resource leaks and battery drain
    for (final discoverer in _discoverers) {
      discoverer.stop();
    }

    _subscriptions.clear();
    _devices.clear();
  }

  void onStatusChanged(DeviceServiceStatus status) {
    for (var s in _subscriptions.values) {
      s.onStatusChanged(status);
    }
  }

  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) {
    Logger.debug("device connection state changed...$deviceId...$state");
    DebugLogManager.logEvent('device_connection_state', {'device_id': deviceId, 'state': state.name});
    if (state == DeviceConnectionState.connected) {
      _userDisconnectedBle = false;
      _resetBleConnectRetryState();
    }
    for (var s in _subscriptions.values) {
      s.onDeviceConnectionStateChanged(deviceId, state);
    }
  }

  void onDevices(List<BtDevice> devices) {
    for (var s in _subscriptions.values) {
      s.onDevices(devices);
    }
  }

  final Mutex _mutex = Mutex();

  Future<DeviceConnection?> ensureConnection(String deviceId, {bool force = false, bool softRetry = false}) async {
    await _mutex.acquire();
    try {
      Logger.debug(
        "ensureConnection ${_connection?.device.id} ${_connection?.status} force=$force softRetry=$softRetry",
      );

      // A force-connect to a different device supersedes any pending soft-retry
      // for the old one. Without this, a stale retry timer can fire later and
      // tear down + replace the connection this call is about to establish.
      if (shouldInvalidatePendingRetryForDifferentTarget(
        pendingRetryDeviceId: _bleConnectRetryDeviceId,
        targetDeviceId: deviceId,
        force: force,
      )) {
        Logger.debug(
          '[DeviceService] invalidating stale soft-retry for $_bleConnectRetryDeviceId (now targeting $deviceId)',
        );
        _resetBleConnectRetryState();
      }

      // Connected to this device — return it
      if (_connection?.device.id == deviceId && _connection?.status == DeviceConnectionState.connected) {
        _resetBleConnectRetryState();
        return _connection;
      }

      // Transport exists for this device but disconnected — native handles reconnection.
      // Don't dispose and recreate the transport; that would cancel native's auto-reconnect.
      // But if force=true (user-initiated), reconnect explicitly.
      if (!force && _connection?.device.id == deviceId) {
        return null;
      }

      // No connection or different device — only connect on force (user-initiated)
      if (!force) return null;

      // App/user asked to reconnect — clear manual-disconnect suppression.
      _userDisconnectedBle = false;

      try {
        await _connectToDevice(deviceId, softRetry: softRetry);
      } on DeviceConnectionException catch (e) {
        Logger.debug(e.cause);
        _scheduleBleConnectRetry(deviceId);
        return null;
      }

      if (_connection?.status == DeviceConnectionState.connected) {
        _firstConnectedAt ??= DateTime.now();
        _resetBleConnectRetryState();
        return _connection;
      }

      // Connect returned without throwing but never reached connected (e.g. no
      // stored device). Schedule a soft retry while the device stays paired.
      _scheduleBleConnectRetry(deviceId);
      return null;
    } finally {
      _mutex.release();
    }
  }

  DateTime? getFirstConnectedAt() {
    return _firstConnectedAt;
  }

  // Helper method to get stored device from SharedPreferences
  BtDevice? _getStoredDevice(String id) {
    try {
      final storedDevice = SharedPreferencesUtil().btDevice;
      if (storedDevice.id == id && storedDevice.id.isNotEmpty) {
        return storedDevice;
      }
    } catch (e) {
      Logger.debug('Error getting stored device: $e');
    }
    return null;
  }

  Future<void> disconnectDevice() async {
    _userDisconnectedBle = true;
    _resetBleConnectRetryState();
    if (_connection != null) {
      Logger.debug("DeviceService: Disconnecting device...");
      await _connection?.disconnect();
      _connection = null;
    }
  }

  Future<void> forgetDevice(String deviceId) async {
    Logger.debug("DeviceService: Forgetting device $deviceId");
    _userDisconnectedBle = true;
    _resetBleConnectRetryState();
    if (_connection != null) {
      if (_connection!.status == DeviceConnectionState.connected) {
        try {
          await _connection!.disconnect();
        } catch (e) {
          Logger.debug("DeviceService: disconnect during forget failed: $e");
        }
      }

      try {
        await _connection!.transport.dispose();
      } catch (e) {
        Logger.debug("DeviceService: transport dispose during forget failed: $e");
      }
      _connection = null;
    }

    _devices.removeWhere((d) => d.id == deviceId);
  }
}
