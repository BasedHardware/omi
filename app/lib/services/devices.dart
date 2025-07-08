import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/errors.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/bluetooth/bluetooth_adapter.dart';

abstract class IDeviceService {
  void start();
  void stop();
  Future<void> discover({String? desirableDeviceId, int timeout = 5});

  Future<DeviceConnection?> ensureConnection(String deviceId, {bool force = false});

  void subscribe(IDeviceServiceSubsciption subscription, Object context);
  void unsubscribe(Object context);

  DateTime? getFirstConnectedAt();
  
  // Battery optimization methods
  void enableBatteryOptimization();
  void disableBatteryOptimization();
  bool get isBatteryOptimized;
}

enum DeviceServiceStatus {
  init,
  ready,
  scanning,
  stop,
}

enum DeviceConnectionState {
  connected,
  disconnected,
}

abstract class IDeviceServiceSubsciption {
  void onDevices(List<BtDevice> devices);
  void onStatusChanged(DeviceServiceStatus status);
  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state);
}

class DeviceService implements IDeviceService {
  DeviceServiceStatus _status = DeviceServiceStatus.init;
  List<BtDevice> _devices = [];
  List<ScanResult> _bleDevices = [];

  final Map<Object, IDeviceServiceSubsciption> _subscriptions = {};

  DeviceConnection? _connection;

  List<BtDevice> get devices => _devices;

  DeviceServiceStatus get status => _status;

  DateTime? _firstConnectedAt;

  // Battery optimization properties
  bool _isBatteryOptimized = false;
  Timer? _scanTimer;
  Timer? _connectionCheckTimer;
  int _scanAttempts = 0;
  static const int _maxScanAttempts = 5;
  static const int _scanInterval = 300; // 5 minutes
  static const int _connectionCheckInterval = 60; // 1 minute

  @override
  bool get isBatteryOptimized => _isBatteryOptimized;

  @override
  void enableBatteryOptimization() {
    _isBatteryOptimized = true;
    debugPrint('DeviceService: Battery optimization enabled');
    
    // Stop continuous scanning
    _stopContinuousScanning();
    
    // Set up optimized scanning
    _setupOptimizedScanning();
    
    // Set up connection monitoring
    _setupConnectionMonitoring();
  }

  @override
  void disableBatteryOptimization() {
    _isBatteryOptimized = false;
    debugPrint('DeviceService: Battery optimization disabled');
    
    // Stop optimized scanning
    _scanTimer?.cancel();
    _connectionCheckTimer?.cancel();
    
    // Restore normal behavior
    _restoreNormalScanning();
  }

  void _stopContinuousScanning() {
    if (_status == DeviceServiceStatus.scanning) {
      BluetoothAdapter.stopScan();
      _status = DeviceServiceStatus.ready;
      debugPrint('DeviceService: Stopped continuous scanning for battery optimization');
    }
  }

  void _setupOptimizedScanning() {
    _scanTimer?.cancel();
    _scanTimer = Timer.periodic(Duration(seconds: _scanInterval), (timer) {
      if (_status == DeviceServiceStatus.ready && _scanAttempts < _maxScanAttempts) {
        _performOptimizedScan();
      }
    });
  }

  void _performOptimizedScan() async {
    if (_isBatteryOptimized) {
      debugPrint('DeviceService: Performing optimized scan attempt ${_scanAttempts + 1}/$_maxScanAttempts');
      
      try {
        await discover(timeout: 10); // Shorter timeout for battery optimization
        _scanAttempts++;
      } catch (e) {
        debugPrint('DeviceService: Optimized scan failed: $e');
        _scanAttempts++;
      }
    }
  }

  void _setupConnectionMonitoring() {
    _connectionCheckTimer?.cancel();
    _connectionCheckTimer = Timer.periodic(Duration(seconds: _connectionCheckInterval), (timer) {
      _checkConnectionHealth();
    });
  }

  void _checkConnectionHealth() async {
    if (_connection?.status == DeviceConnectionState.connected) {
      try {
        // Perform a lightweight connection check
        bool isHealthy = await _connection!.ping();
        if (!isHealthy) {
          debugPrint('DeviceService: Connection health check failed, attempting reconnection');
          await _handleConnectionFailure();
        }
      } catch (e) {
        debugPrint('DeviceService: Connection health check error: $e');
        await _handleConnectionFailure();
      }
    }
  }

  Future<void> _handleConnectionFailure() async {
    if (_connection != null) {
      await _connection!.disconnect();
      _connection = null;
    }
    
    // Attempt reconnection with delay
    Timer(Duration(seconds: 5), () async {
      if (_connection == null) {
        await _attemptReconnection();
      }
    });
  }

  Future<void> _attemptReconnection() async {
    // This would need to be implemented based on the last known device
    debugPrint('DeviceService: Attempting reconnection...');
  }

  void _restoreNormalScanning() {
    debugPrint('DeviceService: Restoring normal scanning behavior');
    // Normal scanning behavior would be restored here
  }

  @override
  Future<void> discover({
    String? desirableDeviceId,
    int timeout = 5,
  }) async {
    debugPrint("Device discovering...");
    if (_status != DeviceServiceStatus.ready) {
      logCommonErrorMessage("Device service is not ready, may busying or stop");
      return;
    }

    if (!(await BluetoothAdapter.isSupported)) {
      logCommonErrorMessage("Bluetooth is not supported");
      return;
    }

    if (BluetoothAdapter.isScanningNow) {
      debugPrint("Device service is scanning...");
      return;
    }

    // Battery optimization: Skip scanning if already have devices and battery is optimized
    if (_isBatteryOptimized && _devices.isNotEmpty && _scanAttempts >= _maxScanAttempts) {
      debugPrint("DeviceService: Skipping scan due to battery optimization");
      return;
    }

    // Listen to scan results, always re-emits previous results
    var discoverSubscription = BluetoothAdapter.scanResults.listen(
      (results) async {
        await _onBleDiscovered(results, desirableDeviceId);
      },
      onError: (e) {
        debugPrint('bleFindDevices error: $e');
      },
    );
    BluetoothAdapter.cancelWhenScanComplete(discoverSubscription);

    // Only look for devices that implement Omi or Frame main service
    _status = DeviceServiceStatus.scanning;
    await BluetoothAdapter.adapterState.where((val) => val == BluetoothAdapterStateHelper.on).first;
    
    // Battery optimization: Use shorter scan duration
    int scanTimeout = _isBatteryOptimized ? timeout ~/ 2 : timeout;
    
    await BluetoothAdapter.startScan(
      timeout: Duration(seconds: scanTimeout),
      withServices: [BluetoothAdapter.createGuid(omiServiceUuid), BluetoothAdapter.createGuid(frameServiceUuid)],
    );
    _status = DeviceServiceStatus.ready;
  }

  Future<void> _onBleDiscovered(List<dynamic> results, String? desirableDeviceId) async {
    _bleDevices = results.cast<ScanResult>().where((r) => r.device.platformName.isNotEmpty).toList();
    _bleDevices.sort((a, b) => b.rssi.compareTo(a.rssi));
    _devices = _bleDevices.map<BtDevice>((e) => BtDevice.fromScanResult(e)).toList();
    onDevices(devices);

    // Check desirable device
    if (desirableDeviceId != null && desirableDeviceId.isNotEmpty) {
      await ensureConnection(desirableDeviceId, force: true);
    }
  }

  Future<void> _connectToDevice(String id) async {
    // Drop exist connection first
    if (_connection?.status == DeviceConnectionState.connected) {
      await _connection?.disconnect();
    }
    _connection = null;

    var bleDevice = _bleDevices.firstWhereOrNull((f) => f.device.remoteId.str == id);
    var device = _devices.firstWhereOrNull((f) => f.id == id);
    if (bleDevice == null || device == null) {
      debugPrint("bleDevice or device is null");
      return;
    }

    // Check exist ble device connection, force disconnect
    if (bleDevice.device.isConnected) {
      await bleDevice.device.disconnect();
    }

    // Then create new connection
    _connection = DeviceConnectionFactory.create(device, bleDevice.device);
    await _connection?.connect(onConnectionStateChanged: onDeviceConnectionStateChanged);
    return;
  }

  @override
  void subscribe(IDeviceServiceSubsciption subscription, Object context) {
    _subscriptions.remove(context.hashCode);
    _subscriptions.putIfAbsent(context.hashCode, () => subscription);

    // Retains
    subscription.onDevices(_devices);
    subscription.onStatusChanged(_status);
  }

  @override
  void unsubscribe(Object context) {
    _subscriptions.remove(context.hashCode);
  }

  @override
  void start() {
    _status = DeviceServiceStatus.ready;

    // Battery optimization: Enable by default for better battery life
    enableBatteryOptimization();

    // TODO: Start watchdog to discover automatically, re-connect automatically
  }

  @override
  void stop() {
    _status = DeviceServiceStatus.stop;
    onStatusChanged(_status);

    // Clean up timers
    _scanTimer?.cancel();
    _connectionCheckTimer?.cancel();

    if (BluetoothAdapter.isScanningNow) {
      BluetoothAdapter.stopScan();
    }
    _subscriptions.clear();
    _devices.clear();
    _bleDevices.clear();
  }

  void onStatusChanged(DeviceServiceStatus status) {
    for (var s in _subscriptions.values) {
      s.onStatusChanged(status);
    }
  }

  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) {
    debugPrint("device connection state changed...${deviceId}...${state}");
    
    // Battery optimization: Reset scan attempts on successful connection
    if (state == DeviceConnectionState.connected) {
      _scanAttempts = 0;
      _firstConnectedAt = DateTime.now();
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

  // Warn: Should use a better solution to prevent race conditions
  bool mutex = false;
  @override
  Future<DeviceConnection?> ensureConnection(String deviceId, {bool force = false}) async {
    while (mutex) {
      await Future.delayed(const Duration(milliseconds: 50));
    }
    mutex = true;

    debugPrint("ensureConnection ${_connection?.device.id} ${_connection?.status} ${force}");

    try {
      // Battery optimization: Skip reconnection if battery is optimized and not forced
      if (_isBatteryOptimized && !force && _connection?.status == DeviceConnectionState.disconnected) {
        debugPrint("DeviceService: Skipping reconnection due to battery optimization");
        return _connection;
      }

      if (_connection?.device.id == deviceId && _connection?.status == DeviceConnectionState.connected && !force) {
        return _connection;
      }

      await _connectToDevice(deviceId);
      return _connection;
    } finally {
      mutex = false;
    }
  }

  @override
  DateTime? getFirstConnectedAt() {
    return _firstConnectedAt;
  }
}
