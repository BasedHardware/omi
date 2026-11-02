import 'dart:async';

import 'package:collection/collection.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/saved_pendant_reconnect.dart';
import 'package:omi/services/devices/transports/native_ble_transport.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
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
  void onDeviceConnectionStateChanged(
    String deviceId,
    DeviceConnectionState state,
  );
}

typedef DeviceConnectionBuilder = DeviceConnection? Function(BtDevice device);

class DeviceService {
  DeviceService(
      {DeviceConnectionBuilder? connectionBuilder,
      bool Function()? reconnectKilled,
      Future<bool> Function()? refreshReconnectKilled})
      : _connectionBuilder = connectionBuilder ?? DeviceConnectionFactory.create {
    savedReconnect = SavedPendantReconnect(
      target: () {
        final device = SharedPreferencesUtil().btDevice;
        return device.id.isNotEmpty && device.locator?.kind == TransportKind.bluetooth ? device.id : null;
      },
      blocked: (id) =>
          _staleBondRecoveryRequired || (!savedReconnect.killed && reconnectPaused) || _manuallyDisconnected(id),
      connected: (id) => _connections[id]?.status == DeviceConnectionState.connected,
      configure: _configureSavedReconnect,
      connect: (id, legacy) async {
        await ensureConnection(id, force: true, automatic: !legacy);
      },
      retire: (id) => disconnectDevice(id),
      observeTarget: (changed) {
        final sub = SharedPreferencesUtil().deviceChanges.listen((_) => changed());
        return () => unawaited(sub.cancel());
      },
      killed: reconnectKilled,
      refreshKilled: refreshReconnectKilled,
    );
  }

  late final SavedPendantReconnect savedReconnect;
  final Set<String> _savedReconnectDevices = {};
  Future<void> _configureSavedReconnect(String id, bool enabled) async {
    // Track in-flight owners too, so stop/retirement can disarm a pending enable.
    enabled ? _savedReconnectDevices.add(id) : _savedReconnectDevices.remove(id);
    final transport = _connections[id]?.transport;
    if (transport is NativeBleTransport) transport.savedReconnectEnabled = enabled;
    try {
      await BleHostApi().configureSavedReconnect(id, enabled);
    } catch (_) {
      if (!enabled) _savedReconnectDevices.add(id); // Keep failed disarms retryable.
      rethrow;
    }
  }

  bool reconnectPaused = false;
  bool _manuallyDisconnected(String id) =>
      !savedReconnect.killed && SharedPreferencesUtil().getStringList('manualBleDisconnects').contains(id);

  bool canAutoReconnectDevice(String id) => !_staleBondRecoveryRequired && !_manuallyDisconnected(id);

  void _setManualDisconnect(String id, bool disconnected) {
    if (savedReconnect.killed) return;
    final ids = SharedPreferencesUtil().getStringList('manualBleDisconnects').toSet();
    disconnected ? ids.add(id) : ids.remove(id);
    SharedPreferencesUtil().saveStringList('manualBleDisconnects', ids.toList());
  }

  Future<void> reconnectSavedDevice(String trigger) async {
    savedReconnect.start();
    await savedReconnect.ensure(trigger);
  }

  final DeviceConnectionBuilder _connectionBuilder;

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

  final Map<String, DeviceConnection> _connections = {};

  DeviceConnection? connectionFor(String deviceId) => _connections[deviceId];
  List<DeviceConnection> get connections => List.unmodifiable(_connections.values);
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
    await _teardownConnection(id);

    var device = _devices.firstWhereOrNull((f) => f.id == id);
    Logger.debug(
      '[DeviceService] device lookup result: ${device?.name ?? "NULL"} (locator: ${device?.locator?.kind})',
    );

    // If device not in discovered list, try to get it from SharedPreferences
    // This allows background reconnection without scanning
    if (device == null) {
      Logger.debug(
        '[DeviceService] Device not in discovered list, checking stored device',
      );
      device = _getStoredDevice(id);
      if (device != null) {
        Logger.debug('[DeviceService] Using stored device: ${device.name}');
        if (!_devices.any((d) => d.id == device!.id)) {
          _devices.add(device);
        }
      } else {
        Logger.debug(
          '[DeviceService] No stored device available for $id, returning',
        );
        return;
      }
    }

    final connection = _connectionBuilder(device);
    if (connection != null) {
      if (connection.transport case final NativeBleTransport transport) {
        transport.savedReconnectEnabled =
            _savedReconnectDevices.contains(id) && SharedPreferencesUtil().btDevice.id == id;
      }
      _connections[id] = connection;
      try {
        await connection.connect(
          onConnectionStateChanged: onDeviceConnectionStateChanged,
        );
      } catch (e) {
        // A disconnect/retirement already owns cleanup once it removes this
        // connection. Its in-flight connect must not unmanage or dispose again.
        if (!identical(_connections[id], connection)) rethrow;
        final isTimeout = e is TimeoutException || (e is DeviceConnectionException && e.isTimeout);
        final transport = connection.transport;
        if (isTimeout ||
            (transport is NativeBleTransport &&
                transport.savedReconnectEnabled &&
                transport.hasRetryableConnectFailure)) {
          // A launch connection attempt timed out waiting for an offline or
          // out-of-range device. Native BLE maintains auto-reconnect in the
          // background; preserve the transport and registration so when the
          // peripheral comes back in range, native device-ready events restore
          // the connection and resume capture.
          rethrow;
        }

        // A native GATT link may already be up even when device-specific
        // initialization (for example, a protected Limitless write) fails.
        // Tear that partial connection down so the UI cannot retain a ghost
        // "connected" device and the next user attempt starts cleanly.
        try {
          await connection.disconnect();
        } catch (e) {
          Logger.debug('[DeviceService] Failed to disconnect partial connection: $e');
        }
        try {
          await connection.transport.dispose();
        } catch (e) {
          Logger.debug('[DeviceService] Failed to dispose partial transport: $e');
        }
        if (identical(_connections[id], connection)) {
          _connections.remove(id);
        }
        rethrow;
      }
    } else {
      Logger.debug(
        '[DeviceService] Failed to create device connection for ${device.id}',
      );
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
    savedReconnect.stop();
    for (final id in _savedReconnectDevices.toList()) {
      await _configureSavedReconnect(id, false);
      if (!_connections.containsKey(id)) await BleHostApi().unmanageDevice(id);
    }
    _status = DeviceServiceStatus.stop;
    onStatusChanged(_status);

    // Stop all discoverers to prevent resource leaks and battery drain
    await stopDiscoverers();

    for (final deviceId in _connections.keys.toList()) {
      await _teardownConnection(deviceId);
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

  void onDeviceConnectionStateChanged(
    String deviceId,
    DeviceConnectionState state,
  ) {
    if (state != DeviceConnectionState.connecting) {
      savedReconnect.stateChanged(deviceId, state == DeviceConnectionState.connected);
    }
    Logger.debug("device connection state changed...$deviceId...$state");
    DebugLogManager.logEvent('device_connection_state', {
      'device_id': deviceId,
      'state': state.name,
    });
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

  Future<DeviceConnection?> ensureConnection(
    String deviceId, {
    bool force = false,
    bool automatic = false,
  }) async {
    await _mutex.acquire();
    try {
      if (automatic && (_manuallyDisconnected(deviceId) || SharedPreferencesUtil().btDevice.id != deviceId)) {
        return null;
      }
      if (!automatic && force) _setManualDisconnect(deviceId, false);
      final existing = _connections[deviceId];
      Logger.debug(
        "ensureConnection $deviceId ${existing?.status} $force",
      );

      if (_staleBondRecoveryRequired) {
        Logger.debug('ensureConnection blocked: stale iOS BLE bond recovery required');
        return null;
      }

      // Connected to this device — return it
      if (existing?.status == DeviceConnectionState.connected && await existing!.transport.isConnected()) {
        return existing;
      }

      // Transport exists for this device but disconnected — native handles reconnection.
      // Don't dispose and recreate the transport; that would cancel native's auto-reconnect.
      // But if force=true (user-initiated), reconnect explicitly.
      if (!force && existing != null) {
        return null;
      }

      // No connection for this device — only connect on force (user-initiated)
      if (!force) return null;

      try {
        if (existing != null &&
            (BleBridge.instance.preservesCaptureIntent(deviceId) ||
                (existing.transport is NativeBleTransport &&
                    (existing.transport as NativeBleTransport).savedReconnectEnabled))) {
          // Preserve the source and its listeners; native manageDevice will
          // establish/discover a real link if the cached transport is down.
          // Go through the connection (not the bare transport) so device setup
          // such as the pendant time sync runs after the link returns, and a
          // transport failure surfaces as DeviceConnectionException like the
          // cold-connect path. Re-pass the service callback so later state
          // changes keep reaching subscribers.
          await existing.connect(onConnectionStateChanged: onDeviceConnectionStateChanged);
        } else {
          await _connectToDevice(deviceId);
        }
      } on DeviceConnectionException catch (e) {
        Logger.debug(e.cause);
        if (automatic) rethrow;
        return null;
      }

      _firstConnectedAt ??= DateTime.now();
      return _connections[deviceId];
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
      final paired = SharedPreferencesUtil().btDevice;
      if (paired.id == id && id.isNotEmpty) return paired;
      return SharedPreferencesUtil().btDevices.firstWhereOrNull(
            (d) => d.id == id && d.id.isNotEmpty,
          );
    } catch (e) {
      Logger.debug('Error getting stored device: $e');
    }
    return null;
  }

  /// A connection leaving [_connections] is always disposed: an orphaned
  /// transport stays registered for native events and would swallow the next
  /// device-ready, leaving the UI disconnected over a live link.
  Future<void> recoverConnection(String deviceId, {required bool Function() shouldRetry}) async {
    await disconnectDevice(deviceId);
    if (!shouldRetry() || SharedPreferencesUtil().btDevice.id != deviceId) return;
    await ensureConnection(deviceId, force: true);
  }

  Future<void> disconnectDevice(String deviceId, {bool userInitiated = false}) async {
    if (userInitiated) _setManualDisconnect(deviceId, true);
    if (userInitiated || reconnectPaused || _staleBondRecoveryRequired || _manuallyDisconnected(deviceId)) {
      // Explicit retirement precedes transport release. Capture recovery leaves
      // native saved intent armed even if its Dart continuation is cancelled.
      try {
        await _configureSavedReconnect(deviceId, false);
      } catch (e) {
        // Keep the failed disarm retryable, but never strand explicit teardown.
        Logger.debug("DeviceService: saved reconnect disarm for $deviceId failed: $e");
      }
    }
    final connection = _connections.remove(deviceId);
    if (connection == null) {
      await BleHostApi().unmanageDevice(deviceId);
      return;
    }
    Logger.debug("DeviceService: Disconnecting device $deviceId...");
    try {
      await connection.disconnect();
    } finally {
      await connection.transport.dispose();
    }
  }

  Future<void> _teardownConnection(String deviceId) async {
    final connection = _connections.remove(deviceId);
    if (connection == null) return;
    if (connection.status == DeviceConnectionState.connected ||
        (!savedReconnect.killed && connection.transport is NativeBleTransport)) {
      try {
        await connection.disconnect();
      } catch (e) {
        Logger.debug("DeviceService: disconnect for $deviceId failed: $e");
      }
    }
    try {
      await connection.transport.dispose();
    } catch (e) {
      Logger.debug("DeviceService: transport dispose for $deviceId failed: $e");
    }
  }

  Future<void> forgetDevice(String deviceId) async {
    Logger.debug("DeviceService: Forgetting device $deviceId");
    _setManualDisconnect(deviceId, true);
    await _configureSavedReconnect(deviceId, false);
    clearStaleBondRecoveryRequirement();
    if (_connections.containsKey(deviceId)) {
      await _teardownConnection(deviceId);
    } else {
      await BleHostApi().unmanageDevice(deviceId);
    }

    _devices.removeWhere((d) => d.id == deviceId);
  }
}
