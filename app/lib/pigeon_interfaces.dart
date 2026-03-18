import 'package:pigeon/pigeon.dart';

@ConfigurePigeon(PigeonOptions(
  dartOut: 'lib/gen/pigeon_communicator.g.dart',
  dartOptions: DartOptions(),
  swiftOut: 'ios/Runner/PigeonCommunicator.g.swift',
  swiftOptions: SwiftOptions(),
  kotlinOut: 'android/app/src/main/kotlin/com/friend/ios/PigeonCommunicator.g.kt',
  kotlinOptions: KotlinOptions(package: 'com.friend.ios'),
  dartPackageName: 'omi_pigeon',
))

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

  BlePeripheral({
    required this.uuid,
    required this.name,
    required this.rssi,
    required this.serviceUuids,
  });
}

/// Discovered BLE service with its characteristic UUIDs.
class BleService {
  final String uuid;
  final List<String> characteristicUuids;

  BleService({required this.uuid, required this.characteristicUuids});
}

/// Dart → Swift: commands sent from Flutter to the native BLE module.
@HostApi()
abstract class BleHostApi {
  // Scanning
  @SwiftFunction('startScan(timeout:serviceUuids:)')
  void startScan(int timeoutSeconds, List<String> serviceUuids);

  @SwiftFunction('stopScan()')
  void stopScan();

  // Connection
  @SwiftFunction('connectPeripheral(uuid:)')
  void connectPeripheral(String uuid);

  @SwiftFunction('disconnectPeripheral(uuid:)')
  void disconnectPeripheral(String uuid);

  /// Reconnect a previously-paired peripheral using retrievePeripherals(withIdentifiers:).
  /// No active scanning — iOS handles reconnection at the chipset level.
  @SwiftFunction('reconnectKnownPeripheral(uuid:)')
  void reconnectKnownPeripheral(String uuid);

  // Service discovery
  @SwiftFunction('discoverServices(peripheralUuid:)')
  void discoverServices(String peripheralUuid);

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

  /// Enable or disable audio batching. When enabled, audio characteristic
  /// notifications are coalesced every ~60ms into a single bridge call.
  @SwiftFunction('setAudioBatchingEnabled(enabled:)')
  void setAudioBatchingEnabled(bool enabled);

  /// Register a characteristic UUID as an audio stream. Notifications for this
  /// characteristic will be batched when audio batching is enabled.
  @SwiftFunction('registerAudioCharacteristic(characteristicUuid:)')
  void registerAudioCharacteristic(String characteristicUuid);

  /// (Android only) Initiate CompanionDeviceManager association for a device.
  /// Shows the system chooser dialog filtered to this device's address.
  /// Returns the associated device address on success, empty string on failure/cancel.
  /// On iOS, returns empty string (state restoration handles background reconnection).
  @async
  @SwiftFunction('requestCompanionDeviceAssociation(deviceAddress:)')
  String requestCompanionDeviceAssociation(String deviceAddress);
}

/// Swift → Dart: events pushed from the native BLE module to Flutter.
@FlutterApi()
abstract class BleFlutterApi {
  void onBluetoothStateChanged(String state);

  void onPeripheralDiscovered(BlePeripheral peripheral);

  void onPeripheralConnected(String peripheralUuid);

  void onPeripheralDisconnected(String peripheralUuid, String? error);

  void onServicesDiscovered(String peripheralUuid, List<BleService> services);

  /// Individual characteristic value update (non-audio characteristics).
  void onCharacteristicValueUpdated(
    String peripheralUuid,
    String serviceUuid,
    String characteristicUuid,
    Uint8List value,
  );

  /// Batched audio data — multiple BLE notifications coalesced into one bridge call.
  /// [batchedData] is the concatenated raw bytes from [notificationCount] notifications.
  void onAudioBatchReceived(
    String peripheralUuid,
    String serviceUuid,
    String characteristicUuid,
    Uint8List batchedData,
    int notificationCount,
  );

  /// Called after app relaunch when iOS restores previously-connected peripherals.
  void onStateRestored(List<String> peripheralUuids);
}
