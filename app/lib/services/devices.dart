import 'dart:async';

import 'package:collection/collection.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/discovery/apple_watch_discoverer.dart';
import 'package:omi/services/devices/discovery/rayban_meta_discoverer.dart';
import 'package:omi/services/devices/discovery/device_discoverer.dart';
import 'package:omi/services/devices/discovery/native_bluetooth_discoverer.dart';
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

typedef DeviceConnectionFactoryFn = DeviceConnection? Function(BtDevice device);

class DeviceService {
  DeviceService({DeviceConnectionFactoryFn? connectionFactory})
      : _connectionFactory = connectionFactory ?? DeviceConnectionFactory.create;

  final DeviceConnectionFactoryFn _connectionFactory;

  DeviceServiceStatus _status = DeviceServiceStatus.init;
  List<BtDevice> _devices = [];
  Future<void>? _activeDiscovery;
  Future<void>? _queuedDiscovery;

  final List<DeviceDiscoverer> _discoverers = [
    NativeBluetoothDiscoverer(),
    AppleWatchDiscoverer(),
    RayBanMetaDiscoverer(),
  ];

  final Map<Object, IDeviceServiceSubsciption> _subscriptions = {};

  /// One connection per device id. Several devices can be connected at the
  /// same time (e.g. an Omi pendant for audio plus OmiGlass for photos); each
  /// one owns its own transport and native BLE registration.
  final Map<String, DeviceConnection> _connections = {};

  /// Connections whose transport currently reports `connected`.
  List<DeviceConnection> get connectedConnections =>
      _connections.values.where((c) => c.status == DeviceConnectionState.connected).toList();

  /// The connection tracked for [deviceId], connected or not.
  DeviceConnection? connectionFor(String deviceId) => _connections[deviceId];

  List<BtDevice> get devices => _devices;

  DeviceServiceStatus get status => _status;

  /// When iOS reports a stale bond (pairing_lost / CB error 14), automatic reconnect
  /// loops are blocked until the user forgets the device in Settings and explicitly retries.
  bool _staleBondRecoveryRequired = false;
  bool get staleBondRecoveryRequired => _staleBondRecoveryRequired;

  void requireStaleBondRecovery() {
    _staleBondRecoveryRequired = true;
  }

  void clearStaleBondRecoveryRequirement() {
    _staleBondRecoveryRequired = false;
  }

  DateTime? _firstConnectedAt;

  /// Runs one follow-up scan when a caller retries while the current scan is
  /// still winding down. In particular, this makes the Bluetooth-enable
  /// recovery action reliable instead of silently returning while a blocked
  /// scan still owns the service.
  Future<void> discover({String? desirableDeviceId, int timeout = 5}) {
    if (_queuedDiscovery != null) return _queuedDiscovery!;
    if (_status == DeviceServiceStatus.scanning) {
      final activeDiscovery = _activeDiscovery;
      if (activeDiscovery == null) return Future.value();
      return _queuedDiscovery ??= activeDiscovery.then<void>(
        (_) => _runQueuedDiscovery(desirableDeviceId: desirableDeviceId, timeout: timeout),
        onError: (_, __) => _runQueuedDiscovery(desirableDeviceId: desirableDeviceId, timeout: timeout),
      );
    }
    if (_status != DeviceServiceStatus.ready) {
      Logger.debug('Device service is not ready, may busying or stop');
      return Future.value();
    }
    return _discover(desirableDeviceId: desirableDeviceId, timeout: timeout);
  }

  Future<void> _runQueuedDiscovery({String? desirableDeviceId, required int timeout}) async {
    _queuedDiscovery = null;
    await discover(desirableDeviceId: desirableDeviceId, timeout: timeout);
  }

  Future<void> _discover({String? desirableDeviceId, required int timeout}) async {
    Logger.debug("Device discovering...");
    final completion = Completer<void>();
    _activeDiscovery = completion.future;
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
      if (!completion.isCompleted) completion.complete();
      _activeDiscovery = null;
    }
  }

  Future<void> _connectToDevice(String id) async {
    // Replace only this device's connection. Other devices stay connected so an
    // Omi pendant and OmiGlass can be attached simultaneously.
    // Caller holds the per-device mutex (see [ensureConnection]).
    await _disposeConnectionUnlocked(id);

    var device = _devices.firstWhereOrNull((f) => f.id == id);
    Logger.debug('[DeviceService] device lookup result: ${device?.name ?? "NULL"} (locator: ${device?.locator?.kind})');

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

    final connection = _connectionFactory(device);
    if (connection == null) {
      Logger.debug('[DeviceService] Failed to create device connection for ${device.id}');
      return;
    }
    _connections[id] = connection;
    await connection.connect(onConnectionStateChanged: onDeviceConnectionStateChanged);
  }

  Future<void> _disposeConnectionUnlocked(String id) async {
    final existing = _connections.remove(id);
    if (existing == null) return;
    if (existing.status == DeviceConnectionState.connected) {
      try {
        await existing.disconnect();
      } catch (e) {
        Logger.debug('[DeviceService] disconnect during dispose failed: $e');
      }
    }
    try {
      await existing.transport.dispose();
    } catch (e) {
      Logger.debug('[DeviceService] transport dispose failed: $e');
    }
  }

  Future<void> _disposeConnection(String id) async {
    final mutex = _connectionMutexes.putIfAbsent(id, Mutex.new);
    await mutex.acquire();
    try {
      await _disposeConnectionUnlocked(id);
    } finally {
      mutex.release();
    }
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

    // TODO: Start watchdog to discover automatically, re-connect automatically
  }

  Future<void> stop() async {
    _status = DeviceServiceStatus.stop;
    onStatusChanged(_status);

    // Stop all discoverers to prevent resource leaks and battery drain
    await stopDiscoverers();

    for (final deviceId in _connections.keys.toList()) {
      await _disposeConnection(deviceId);
    }

    _subscriptions.clear();
    _devices.clear();
  }

  Future<void> stopDiscoverers() async {
    for (final discoverer in _discoverers) {
      try {
        await discoverer.stop();
      } catch (e) {
        Logger.debug('DeviceService.stopDiscoverers: $e');
      }
    }
  }

  void onStatusChanged(DeviceServiceStatus status) {
    for (var s in _subscriptions.values) {
      s.onStatusChanged(status);
    }
  }

  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) {
    Logger.debug("device connection state changed...$deviceId...$state");
    DebugLogManager.logEvent('device_connection_state', {'device_id': deviceId, 'state': state.name});
    for (var s in _subscriptions.values) {
      s.onDeviceConnectionStateChanged(deviceId, state);
    }
  }

  void onDevices(List<BtDevice> devices) {
    for (var s in _subscriptions.values) {
      s.onDevices(devices);
    }
  }

  /// One mutex per device: a pendant that is out of range (60 s connect
  /// timeout) must not hold up the glasses sitting next to the phone.
  final Map<String, Mutex> _connectionMutexes = {};

  Future<DeviceConnection?> ensureConnection(String deviceId, {bool force = false}) async {
    final mutex = _connectionMutexes.putIfAbsent(deviceId, Mutex.new);
    await mutex.acquire();
    try {
      final existing = _connections[deviceId];
      Logger.debug("ensureConnection $deviceId ${existing?.status} $force");

      if (_staleBondRecoveryRequired) {
        Logger.debug('ensureConnection blocked: stale iOS BLE bond recovery required');
        return null;
      }

      // Connected to this device — return it
      if (existing?.status == DeviceConnectionState.connected) {
        return existing;
      }

      // Transport exists for this device but disconnected — native handles reconnection.
      // Don't dispose and recreate the transport; that would cancel native's auto-reconnect.
      // But if force=true (user-initiated), reconnect explicitly.
      // No connection at all — only connect on force (user-initiated).
      if (!force) return null;

      try {
        await _connectToDevice(deviceId);
      } on DeviceConnectionException catch (e) {
        Logger.debug(e.cause);
        return null;
      }

      _firstConnectedAt ??= DateTime.now();
      return _connections[deviceId];
    } finally {
      mutex.release();
    }
  }

  DateTime? getFirstConnectedAt() {
    return _firstConnectedAt;
  }

  // Helper method to get stored device from SharedPreferences. Both the primary
  // device and the companion (e.g. OmiGlass paired next to an Omi) are eligible
  // for background reconnection without a scan.
  BtDevice? _getStoredDevice(String id) {
    if (id.isEmpty) return null;
    try {
      final preferences = SharedPreferencesUtil();
      for (final storedDevice in [preferences.btDevice, preferences.companionBtDevice, ...preferences.btDevices]) {
        if (storedDevice != null && storedDevice.id == id) {
          return storedDevice;
        }
      }
    } catch (e) {
      Logger.debug('Error getting stored device: $e');
    }
    return null;
  }

  /// Drops the BLE link for [deviceId] (e.g. before a DFU reboot). The
  /// connection object stays tracked so a later forced [ensureConnection]
  /// disposes its transport before creating a fresh one.
  Future<void> disconnectDevice(String deviceId) async {
    final mutex = _connectionMutexes.putIfAbsent(deviceId, Mutex.new);
    await mutex.acquire();
    try {
      final connection = _connections[deviceId];
      if (connection == null) return;
      Logger.debug("DeviceService: Disconnecting device $deviceId...");
      await connection.disconnect();
    } finally {
      mutex.release();
    }
  }

  Future<void> forgetDevice(String deviceId) async {
    final mutex = _connectionMutexes.putIfAbsent(deviceId, Mutex.new);
    await mutex.acquire();
    try {
      Logger.debug("DeviceService: Forgetting device $deviceId");
      clearStaleBondRecoveryRequirement();
      await _disposeConnectionUnlocked(deviceId);
      _devices.removeWhere((d) => d.id == deviceId);
    } finally {
      mutex.release();
    }
  }
}
