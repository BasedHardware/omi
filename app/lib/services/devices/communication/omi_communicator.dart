import 'dart:async';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:omi/services/devices/communication/device_communicator.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/utils/bluetooth/bluetooth_adapter.dart';

class OmiCommunicator extends DeviceCommunicator {
  final BluetoothDevice _bleDevice;
  final StreamController<Map<String, dynamic>> _messageController;
  final StreamController<DeviceConnectionState> _connectionStateController;

  OmiCommunicator(this._bleDevice)
      : _messageController = StreamController<Map<String, dynamic>>.broadcast(),
        _connectionStateController = StreamController<DeviceConnectionState>.broadcast();

  @override
  String get deviceId => _bleDevice.remoteId.str;

  @override
  DeviceConnectionState get connectionState =>
      _bleDevice.isConnected ? DeviceConnectionState.connected : DeviceConnectionState.disconnected;

  @override
  Stream<DeviceConnectionState> get connectionStateStream => _connectionStateController.stream;

  @override
  Future<void> connect() async {
    // Wait for adapter to be on
    await BluetoothAdapter.adapterState.where((val) => val == BluetoothAdapterStateHelper.on).first;

    // Connect to device
    await _bleDevice.connect();
    await _bleDevice.connectionState.where((val) => val == BluetoothConnectionState.connected).first;

    // Request MTU for Android
    if (Platform.isAndroid && _bleDevice.mtuNow < 512) {
      await _bleDevice.requestMtu(512);
    }

    // Discover services
    await _bleDevice.discoverServices();

    _connectionStateController.add(DeviceConnectionState.connected);
  }

  @override
  Future<void> disconnect() async {
    await _bleDevice.disconnect();
    _connectionStateController.add(DeviceConnectionState.disconnected);
  }

  @override
  Future<bool> isConnected() async {
    return _bleDevice.isConnected;
  }

  @override
  Future<Map<String, dynamic>?> sendCommand(String command, [Map<String, dynamic>? params]) async {
    switch (command) {
      case 'getBattery':
        return await _getBatteryLevel();
      case 'getAudioCodec':
        return await _getAudioCodec();
      case 'startAudioStream':
        return await _startAudioStream(params?['onAudioReceived']);
      case 'getButtonState':
        return await _getButtonState();
      case 'playHaptic':
        return await _playHaptic(params?['mode'] ?? 1);
      case 'getStorageList':
        return await _getStorageList();
      case 'getFeatures':
        return await _getFeatures();
      case 'setLedDimRatio':
        return await _setLedDimRatio(params?['ratio'] ?? 0);
      case 'getLedDimRatio':
        return await _getLedDimRatio();
      case 'startPhotoCapture':
        return await _startPhotoCapture();
      case 'stopPhotoCapture':
        return await _stopPhotoCapture();
      case 'getAccelData':
        return await _getAccelData();
      default:
        return null;
    }
  }

  @override
  Stream<Map<String, dynamic>> get messageStream => _messageController.stream;

  @override
  Future<void> dispose() async {
    await _messageController.close();
    await _connectionStateController.close();
  }

  // Omi-specific methods
  Future<Map<String, dynamic>> _getBatteryLevel() async {
    final service = await _getService(batteryServiceUuid);
    if (service == null) return {'level': -1};

    final characteristic = _getCharacteristic(service, batteryLevelCharacteristicUuid);
    if (characteristic == null) return {'level': -1};

    final value = await characteristic.read();
    return {'level': value.isNotEmpty ? value[0] : -1};
  }

  Future<Map<String, dynamic>> _getAudioCodec() async {
    final service = await _getService(omiServiceUuid);
    if (service == null) return {'codec': 'pcm8'};

    final characteristic = _getCharacteristic(service, audioCodecCharacteristicUuid);
    if (characteristic == null) return {'codec': 'pcm8'};

    final value = await characteristic.read();
    final codecId = value.isNotEmpty ? value[0] : 1;

    String codecName;
    switch (codecId) {
      case 1:
        codecName = 'pcm8';
        break;
      case 20:
        codecName = 'opus';
        break;
      case 21:
        codecName = 'opusFS320';
        break;
      default:
        codecName = 'pcm8';
    }

    return {'codec': codecName};
  }

  Future<Map<String, dynamic>> _startAudioStream(Function(List<int>)? onAudioReceived) async {
    final service = await _getService(omiServiceUuid);
    if (service == null) return {'success': false, 'error': 'Audio service not found'};

    final characteristic = _getCharacteristic(service, audioDataStreamCharacteristicUuid);
    if (characteristic == null) return {'success': false, 'error': 'Audio characteristic not found'};

    await characteristic.setNotifyValue(true);
    characteristic.lastValueStream.listen((value) {
      onAudioReceived?.call(value);
      _messageController.add({
        'type': 'audioData',
        'data': value,
        'timestamp': DateTime.now().millisecondsSinceEpoch,
      });
    });

    return {'success': true};
  }

  Future<Map<String, dynamic>> _getButtonState() async {
    final service = await _getService(buttonServiceUuid);
    if (service == null) return {'state': <int>[]};

    final characteristic = _getCharacteristic(service, buttonTriggerCharacteristicUuid);
    if (characteristic == null) return {'state': <int>[]};

    final value = await characteristic.read();
    return {'state': value};
  }

  Future<Map<String, dynamic>> _playHaptic(int mode) async {
    final service = await _getService(speakerDataStreamServiceUuid);
    if (service == null) return {'success': false, 'error': 'Speaker service not found'};

    final characteristic = _getCharacteristic(service, speakerDataStreamCharacteristicUuid);
    if (characteristic == null) return {'success': false, 'error': 'Speaker characteristic not found'};

    await characteristic.write([mode & 0xFF]);
    return {'success': true};
  }

  Future<Map<String, dynamic>> _getStorageList() async {
    final service = await _getService(storageDataStreamServiceUuid);
    if (service == null) return {'storageList': <int>[]};

    final characteristic = _getCharacteristic(service, storageReadControlCharacteristicUuid);
    if (characteristic == null) return {'storageList': <int>[]};

    final value = await characteristic.read();
    return {'storageList': value};
  }

  Future<Map<String, dynamic>> _getFeatures() async {
    final service = await _getService('19b10020-e8f2-537e-4f6c-d104768a1214'); // featuresServiceUuid
    if (service == null) return {'features': 0};

    final characteristic =
        _getCharacteristic(service, '19b10021-e8f2-537e-4f6c-d104768a1214'); // featuresCharacteristicUuid
    if (characteristic == null) return {'features': 0};

    final value = await characteristic.read();
    if (value.length >= 4) {
      final features = (value[0] | (value[1] << 8) | (value[2] << 16) | (value[3] << 24)) & 0xFFFFFFFF;
      return {'features': features};
    }
    return {'features': 0};
  }

  Future<Map<String, dynamic>> _setLedDimRatio(int ratio) async {
    final service = await _getService('19b10010-e8f2-537e-4f6c-d104768a1214'); // settingsServiceUuid
    if (service == null) return {'success': false, 'error': 'Settings service not found'};

    final characteristic =
        _getCharacteristic(service, '19b10011-e8f2-537e-4f6c-d104768a1214'); // settingsDimRatioCharacteristicUuid
    if (characteristic == null) return {'success': false, 'error': 'LED dim ratio characteristic not found'};

    await characteristic.write([ratio.clamp(0, 100)]);
    return {'success': true};
  }

  Future<Map<String, dynamic>> _getLedDimRatio() async {
    final service = await _getService('19b10010-e8f2-537e-4f6c-d104768a1214'); // settingsServiceUuid
    if (service == null) return {'ratio': null};

    final characteristic =
        _getCharacteristic(service, '19b10011-e8f2-537e-4f6c-d104768a1214'); // settingsDimRatioCharacteristicUuid
    if (characteristic == null) return {'ratio': null};

    final value = await characteristic.read();
    return {'ratio': value.isNotEmpty ? value[0] : null};
  }

  Future<Map<String, dynamic>> _startPhotoCapture() async {
    final service = await _getService(omiServiceUuid);
    if (service == null) return {'success': false, 'error': 'Omi service not found'};

    final characteristic = _getCharacteristic(service, imageCaptureControlCharacteristicUuid);
    if (characteristic == null) return {'success': false, 'error': 'Image capture control characteristic not found'};

    await characteristic.write([0x05]); // Capture photo every 5s
    return {'success': true};
  }

  Future<Map<String, dynamic>> _stopPhotoCapture() async {
    final service = await _getService(omiServiceUuid);
    if (service == null) return {'success': false, 'error': 'Omi service not found'};

    final characteristic = _getCharacteristic(service, imageCaptureControlCharacteristicUuid);
    if (characteristic == null) return {'success': false, 'error': 'Image capture control characteristic not found'};

    await characteristic.write([0x00]); // Stop capture
    return {'success': true};
  }

  Future<Map<String, dynamic>> _getAccelData() async {
    final service = await _getService(accelDataStreamServiceUuid);
    if (service == null) return {'accelData': <double>[]};

    final characteristic = _getCharacteristic(service, accelDataStreamCharacteristicUuid);
    if (characteristic == null) return {'accelData': <double>[]};

    final value = await characteristic.read();
    if (value.length > 4) {
      final accelData = <double>[];
      for (int i = 0; i < 6; i++) {
        int baseIndex = i * 8;
        if (baseIndex + 7 < value.length) {
          final result = ((value[baseIndex] |
                      (value[baseIndex + 1] << 8) |
                      (value[baseIndex + 2] << 16) |
                      (value[baseIndex + 3] << 24)) &
                  0xFFFFFFFF)
              .toSigned(32);
          final temp = ((value[baseIndex + 4] |
                      (value[baseIndex + 5] << 8) |
                      (value[baseIndex + 6] << 16) |
                      (value[baseIndex + 7] << 24)) &
                  0xFFFFFFFF)
              .toSigned(32);
          final axisValue = result + (temp / 1000000);
          accelData.add(axisValue);
        }
      }
      return {'accelData': accelData};
    }
    return {'accelData': <double>[]};
  }

  Future<BluetoothService?> _getService(String uuid) async {
    final services = await _bleDevice.discoverServices();
    return services.firstWhereOrNull((service) => service.uuid.str128.toLowerCase() == uuid.toLowerCase());
  }

  BluetoothCharacteristic? _getCharacteristic(BluetoothService service, String uuid) {
    return service.characteristics.firstWhereOrNull(
      (characteristic) => characteristic.uuid.str128.toLowerCase() == uuid.toLowerCase(),
    );
  }
}
