import 'package:pigeon/pigeon.dart';

@ConfigurePigeon(
  PigeonOptions(
    dartOut: 'lib/gen/pigeon_communicator.g.dart',
    dartOptions: DartOptions(),
    swiftOut: 'ios/Runner/PigeonCommunicator.g.swift',
    swiftOptions: SwiftOptions(),
    kotlinOut: 'android/app/src/main/kotlin/com/friend/ios/PigeonCommunicator.g.kt',
    kotlinOptions: KotlinOptions(package: 'com.friend.ios'),
    dartPackageName: 'omi_pigeon',
  ),
)
// =============================================================================
// Watch Recorder APIs
// =============================================================================
@HostApi()
abstract class WatchRecorderHostAPI {
  @SwiftFunction('startRecording()')
  void startRecording();
  @SwiftFunction('stopRecording()')
  void stopRecording();
  @SwiftFunction('sendAudioData(audioData:)')
  void sendAudioData(Uint8List audioData);
  @SwiftFunction('sendAudioChunk(audioChunk:chunkIndex:isLast:sampleRate:)')
  void sendAudioChunk(Uint8List audioChunk, int chunkIndex, bool isLast, double sampleRate);
  @SwiftFunction('isWatchPaired()')
  bool isWatchPaired();
  @SwiftFunction('isWatchReachable()')
  bool isWatchReachable();
  @SwiftFunction('isWatchSessionSupported()')
  bool isWatchSessionSupported();
  @SwiftFunction('isWatchAppInstalled()')
  bool isWatchAppInstalled();
  @SwiftFunction('requestWatchMicrophonePermission()')
  void requestWatchMicrophonePermission();
  @SwiftFunction('requestMainAppMicrophonePermission()')
  void requestMainAppMicrophonePermission();
  @SwiftFunction('checkMainAppMicrophonePermission()')
  bool checkMainAppMicrophonePermission();
  @SwiftFunction('getWatchBatteryLevel()')
  double getWatchBatteryLevel();
  @SwiftFunction('getWatchBatteryState()')
  int getWatchBatteryState();
  @SwiftFunction('requestWatchBatteryUpdate()')
  void requestWatchBatteryUpdate();
  @SwiftFunction('getWatchInfo()')
  Map<String, String> getWatchInfo();
}

@FlutterApi()
abstract class WatchRecorderFlutterAPI {
  void onRecordingStarted();
  void onRecordingStopped();
  void onAudioData(Uint8List audioData);
  void onAudioChunk(Uint8List audioChunk, int chunkIndex, bool isLast, double sampleRate);
  void onRecordingError(String error);
  void onMicrophonePermissionResult(bool granted);
  void onMainAppMicrophonePermissionResult(bool granted);
  void onWatchBatteryUpdate(double batteryLevel, int batteryState);
}

// =============================================================================
// BLE APIs
// =============================================================================

/// Discovered BLE peripheral info passed from native to Dart.
class BlePeripheral {
  final String uuid;
  final String name;
  final int rssi;
  final List<String> serviceUuids;

  BlePeripheral({required this.uuid, required this.name, required this.rssi, required this.serviceUuids});
}

/// Discovered BLE service with its characteristic UUIDs.
class BleService {
  final String uuid;
  final List<String> characteristicUuids;

  BleService({required this.uuid, required this.characteristicUuids});
}

/// A single disconnect event stored in native preferences.
class BleDisconnectEvent {
  final int timestamp;
  final String reason;
  final int reasonCode;
  final bool isManual;

  /// Kind of event: "disconnect" (link lost after connect) or "fail_to_connect"
  /// (connect attempt never established). Defaults to "disconnect" for legacy records.
  final String eventType;

  /// Last RSSI sample captured before this event (dBm). 0 if unknown.
  final int lastRssi;

  /// How long the link was established before this event (ms). 0 if unknown
  /// or for fail_to_connect events.
  final int connectionDurationMs;

  /// App lifecycle state at the moment of the event: "foreground", "background",
  /// or "inactive" (iOS transitioning). Empty string if unknown.
  final String appState;

  /// ms between this disconnect and the subsequent successful reconnect.
  /// 0 while the device has not yet reconnected.
  final int timeToReconnectMs;

  /// RSSI trajectory over the ~15s before this event. One of:
  ///   "fading"  — signal declined ≥10 dB before the drop (walk-away)
  ///   "sudden"  — signal stable then link died (interference/stall/device off)
  ///   "gap"     — no recent RSSI samples (keep-alive wasn't running)
  ///   "unknown" — insufficient samples to classify
  /// Empty string on legacy records written before this field existed.
  final String rssiTrend;

  BleDisconnectEvent({
    required this.timestamp,
    required this.reason,
    required this.reasonCode,
    required this.isManual,
    required this.eventType,
    required this.lastRssi,
    required this.connectionDurationMs,
    required this.appState,
    required this.timeToReconnectMs,
    required this.rssiTrend,
  });
}

/// A single battery level reading persisted by the native BLE layer.
class BleBatteryPoint {
  final int timestamp;
  final int level;

  BleBatteryPoint({required this.timestamp, required this.level});
}

/// Diagnostics data read from native preferences on demand.
class BleDeviceDiagnostics {
  final List<BleDisconnectEvent> disconnectHistory;
  final int reconnectionCount;
  final int connectedAt;

  /// Count of connect attempts that never reached didConnect. Surfaces the
  /// silent-failure path separately from established-then-dropped disconnects.
  final int failToConnectCount;

  BleDeviceDiagnostics({
    required this.disconnectHistory,
    required this.reconnectionCount,
    required this.connectedAt,
    required this.failToConnectCount,
  });
}

/// Dart → Native: commands sent from Flutter to the native BLE module.
@HostApi()
abstract class BleHostApi {
  @SwiftFunction('startScan(timeout:serviceUuids:)')
  void startScan(int timeoutSeconds, List<String> serviceUuids);

  @SwiftFunction('stopScan()')
  void stopScan();

  @SwiftFunction('manageDevice(uuid:requiresBond:)')
  void manageDevice(String uuid, bool requiresBond);

  @SwiftFunction('unmanageDevice(uuid:)')
  void unmanageDevice(String uuid);

  @async
  @SwiftFunction('requestBond(uuid:)')
  bool requestBond(String uuid);

  // Characteristic operations
  @async
  @SwiftFunction('readCharacteristic(peripheralUuid:serviceUuid:characteristicUuid:)')
  Uint8List readCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid);

  @async
  @SwiftFunction('writeCharacteristic(peripheralUuid:serviceUuid:characteristicUuid:data:)')
  void writeCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid, Uint8List data);

  @SwiftFunction('subscribeCharacteristic(peripheralUuid:serviceUuid:characteristicUuid:)')
  void subscribeCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid);

  @SwiftFunction('unsubscribeCharacteristic(peripheralUuid:serviceUuid:characteristicUuid:)')
  void unsubscribeCharacteristic(String peripheralUuid, String serviceUuid, String characteristicUuid);

  // State
  @SwiftFunction('getBluetoothState()')
  String getBluetoothState();

  @SwiftFunction('isPeripheralConnected(uuid:)')
  bool isPeripheralConnected(String uuid);

  // Diagnostics
  @SwiftFunction('startRssiStreaming(uuid:)')
  void startRssiStreaming(String uuid);

  @SwiftFunction('stopRssiStreaming(uuid:)')
  void stopRssiStreaming(String uuid);

  @async
  @SwiftFunction('getDeviceDiagnostics(uuid:)')
  BleDeviceDiagnostics getDeviceDiagnostics(String uuid);

  @async
  @SwiftFunction('getBatteryHistory(uuid:)')
  List<BleBatteryPoint> getBatteryHistory(String uuid);

  /// (Android only) Check if any CompanionDeviceManager association exists.
  @SwiftFunction('hasCompanionDeviceAssociation()')
  bool hasCompanionDeviceAssociation();

  /// (Android only) Initiate CompanionDeviceManager association for a device.
  @async
  @SwiftFunction('requestCompanionDeviceAssociation(deviceAddress:)')
  String requestCompanionDeviceAssociation(String deviceAddress);
}

@FlutterApi()
abstract class BleFlutterApi {
  void onBluetoothStateChanged(String state);

  void onPeripheralDiscovered(BlePeripheral peripheral);

  void onDeviceReady(String peripheralUuid, List<BleService> services);

  void onPeripheralDisconnected(String peripheralUuid, String? error);

  void onCharacteristicValueUpdated(
    String peripheralUuid,
    String serviceUuid,
    String characteristicUuid,
    Uint8List value,
  );

  void onRssiUpdate(String peripheralUuid, int rssi);

  void onStateRestored(List<String> peripheralUuids);
}
