import 'dart:async';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/device_connection.dart';
import 'package:omi/services/devices/models.dart';

abstract class CustomDeviceConnection extends DeviceConnection {
  String get serviceUuid;
  String get controlCharacteristicUuid;
  String get audioCharacteristicUuid;
  BleAudioCodec get audioCodec;

  int get unmuteCommandCode;
  int get muteCommandCode;
  int get batteryCommandCode;

  List<int> get unmuteCommandData;
  List<int> get muteCommandData;

  Map<String, dynamic> parseResponse(List<int> data);
  List<int>? processAudioPacket(List<int> data);
  Map<String, dynamic>? parseBatteryResponse(List<int> payload);

  final _audioController = StreamController<List<int>>.broadcast();
  final _responseControllers = <int, Completer<List<int>>>{};

  StreamSubscription? _controlSub;
  StreamSubscription? _audioSub;
  bool _isRecording = false;

  CustomDeviceConnection(super.device, super.transport);

  @override
  Future<void> connect({
    Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged,
    bool autoConnect = false,
  }) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged, autoConnect: autoConnect);
    await Future.delayed(const Duration(seconds: 1));

    _controlSub = transport.getCharacteristicStream(serviceUuid, controlCharacteristicUuid).listen((data) {
      final response = parseResponse(data);

      if (response['type'] == 'response') {
        final cmdId = response['code'] as int;
        final payload = response['payload'] as List<int>;

        if (_responseControllers.containsKey(cmdId) && !_responseControllers[cmdId]!.isCompleted) {
          _responseControllers[cmdId]?.complete(payload);
        }
      }
    });

    _audioSub = transport.getCharacteristicStream(serviceUuid, audioCharacteristicUuid).listen((data) {
      final payload = processAudioPacket(data);
      if (payload != null && payload.isNotEmpty) {
        _audioController.add(payload);
      }
    });
  }

  @override
  Future<void> disconnect() async {
    if (_isRecording) {
      try {
        await _sendCommand(muteCommandCode, muteCommandData);
      } catch (_) {}
    }
    await _controlSub?.cancel();
    await _audioSub?.cancel();
    await _audioController.close();
    await super.disconnect();
  }

  Future<List<int>?> _sendCommand(int cmdId, List<int> payload) async {
    final completer = Completer<List<int>>();
    _responseControllers[cmdId] = completer;

    try {
      final command = encodeCommand(cmdId, payload);
      await transport.writeCharacteristic(serviceUuid, controlCharacteristicUuid, command);
      return await completer.future.timeout(const Duration(seconds: 5));
    } on TimeoutException {
      return null;
    } finally {
      _responseControllers.remove(cmdId);
    }
  }

  @override
  Future<int> performRetrieveBatteryLevel() async {
    final response = await _sendCommand(batteryCommandCode, []);
    if (response != null) {
      final batteryInfo = parseBatteryResponse(response);
      if (batteryInfo != null) {
        return batteryInfo['level'] as int;
      }
    }
    return -1;
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int)? onBatteryLevelChange,
  }) async {
    if (onBatteryLevelChange == null) return null;

    final controller = StreamController<List<int>>();
    int? lastLevel;

    final timer = Timer.periodic(const Duration(seconds: 60), (timer) async {
      final level = await performRetrieveBatteryLevel();
      if (level >= 0 && level != lastLevel) {
        lastLevel = level;
        onBatteryLevelChange(level);
      }
    });

    controller.onCancel = () => timer.cancel();

    final initialLevel = await performRetrieveBatteryLevel();
    if (initialLevel >= 0) {
      lastLevel = initialLevel;
      onBatteryLevelChange(initialLevel);
    }

    return controller.stream.listen(null);
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async => audioCodec;

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    await _sendCommand(unmuteCommandCode, unmuteCommandData);
    _isRecording = true;
    return _audioController.stream.listen(onAudioBytesReceived);
  }

  @override
  Future<List<int>> performGetButtonState() async => [];

  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int>) onStorageBytesReceived,
  }) async =>
      null;

  @override
  Future performCameraStartPhotoController() async {}

  @override
  Future performCameraStopPhotoController() async {}

  @override
  Future<bool> performHasPhotoStreamingCharacteristic() async => false;

  @override
  Future<StreamSubscription?> performGetImageListener({
    required void Function(OrientedImage orientedImage) onImageReceived,
  }) async =>
      null;

  @override
  Future<StreamSubscription<List<int>>?> performGetAccelListener({
    void Function(int)? onAccelChange,
  }) async =>
      null;

  @override
  Future<int> performGetFeatures() async => 0;

  @override
  Future<void> performSetLedDimRatio(int ratio) async {}

  @override
  Future<int?> performGetLedDimRatio() async => null;

  @override
  Future<void> performSetMicGain(int gain) async {}

  @override
  Future<int?> performGetMicGain() async => null;

  List<int> encodeCommand(int commandCode, List<int> data) {
    return [commandCode & 0xFF, (commandCode >> 8) & 0xFF, ...data];
  }
}
