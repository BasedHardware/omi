import 'dart:async';
import 'dart:typed_data';

import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/rayban_meta_bridge.dart';
import 'package:omi/utils/logger.dart';
import 'device_transport.dart';

/// Transport for Ray-Ban Meta glasses.
///
/// Camera/photo events come from the Meta Wearables Device Access Toolkit
/// through the native bridge; microphone audio comes from the platform
/// Bluetooth HFP route (the toolkit has no mic API). Both are exposed through
/// the same synthetic characteristic-stream vocabulary the rest of the device
/// layer speaks, mirroring WatchTransport.
class RayBanMetaTransport extends DeviceTransport {
  final String _deviceId;
  final RayBanMetaHostAPI _hostAPI = RayBanMetaHostAPI();
  final StreamController<DeviceTransportState> _connectionStateController;
  final Map<String, StreamController<List<int>>> _streamControllers = {};

  DeviceTransportState _state = DeviceTransportState.disconnected;

  static RayBanMetaFlutterBridge? _bridge;
  static final List<StreamController<List<int>>> _audioControllers = [];
  static final List<StreamController<List<int>>> _photoControllers = [];
  static final List<RayBanMetaTransport> _instances = [];

  static bool _lastGlassesRouteActive = false;
  static String _lastCameraState = 'stopped';

  RayBanMetaTransport(this._deviceId)
      : _connectionStateController = StreamController<DeviceTransportState>.broadcast() {
    _ensureBridgeSetup();
    _instances.add(this);
  }

  @override
  String get deviceId => _deviceId;

  @override
  Stream<DeviceTransportState> get connectionStateStream => _connectionStateController.stream;

  /// Whether the glasses' HFP mic was the active input route at last report.
  static bool get glassesAudioRouteActive => _lastGlassesRouteActive;

  /// Last reported DAT camera stream state ('stopped'|'starting'|'streaming'|'paused').
  static String get cameraState => _lastCameraState;

  /// Photo events cross the characteristic-stream seam as plain bytes: one
  /// orientation byte (degrees / 90 → 0..3, matching ImageOrientation values)
  /// followed by the JPEG payload.
  static List<int> framePhotoEvent(Uint8List jpegBytes, int orientationDegrees) {
    return <int>[(orientationDegrees ~/ 90) & 0x03, ...jpegBytes];
  }

  void _updateState(DeviceTransportState newState) {
    if (_state != newState) {
      _state = newState;
      _connectionStateController.add(_state);
    }
  }

  static void _ensureBridgeSetup() {
    if (_bridge == null) {
      _bridge = RayBanMetaFlutterBridge(
        onAudioFrameCb: (Uint8List frame, double sampleRate) {
          _audioControllers.removeWhere((controller) => controller.isClosed);
          for (final controller in _audioControllers) {
            try {
              controller.add(frame);
            } catch (e) {
              Logger.debug('RayBanMeta Transport: Error forwarding audio: $e');
            }
          }
        },
        onPhotoCapturedCb: (Uint8List jpegBytes, int orientationDegrees) {
          _photoControllers.removeWhere((controller) => controller.isClosed);
          final framed = framePhotoEvent(jpegBytes, orientationDegrees);
          for (final controller in _photoControllers) {
            try {
              controller.add(framed);
            } catch (e) {
              Logger.debug('RayBanMeta Transport: Error forwarding photo: $e');
            }
          }
        },
        onAudioRouteChangedCb: (bool active) {
          _lastGlassesRouteActive = active;
          Logger.debug('RayBanMeta Transport: glasses audio route active=$active');
        },
        onCameraStateChangedCb: (String state) {
          _lastCameraState = state;
          Logger.debug('RayBanMeta Transport: camera state=$state');
        },
        onConnectionStateChangedCb: (String deviceId, String state) {
          for (final transport in _instances) {
            if (transport._deviceId != deviceId) continue;
            switch (state) {
              case 'connected':
                transport._updateState(DeviceTransportState.connected);
                break;
              case 'connecting':
                transport._updateState(DeviceTransportState.connecting);
                break;
              default:
                transport._updateState(DeviceTransportState.disconnected);
            }
          }
        },
        onErrorCb: (String code, String message) {
          Logger.debug('RayBanMeta Transport: native error $code: $message');
        },
      );
      RayBanMetaFlutterAPI.setUp(_bridge!);
    }
  }

  @override
  Future<void> connect() async {
    if (_state == DeviceTransportState.connected) {
      return;
    }

    _updateState(DeviceTransportState.connecting);

    try {
      final mode = await _hostAPI.getAvailabilityMode();
      if (mode == 'none') {
        throw Exception('Ray-Ban Meta support is not available in this build');
      }

      if (mode == 'full') {
        await _hostAPI.connect(_deviceId);
        // Native pushes onConnectionStateChanged; poll as a fallback so a
        // missed event can't wedge us in `connecting` forever.
        for (var i = 0; i < 20; i++) {
          final state = await _hostAPI.getConnectionState();
          if (state == 'connected') {
            _updateState(DeviceTransportState.connected);
            return;
          }
          await Future.delayed(const Duration(milliseconds: 500));
        }
        _updateState(DeviceTransportState.disconnected);
        throw Exception('Timed out connecting to Ray-Ban Meta glasses');
      }

      // Audio-only fallback: the user-selected HFP port UID is authoritative.
      // Names are renameable and only participate in initial discovery.
      final inputs = await _hostAPI.getBluetoothHfpInputs();
      if (!inputs.any((input) => input.uid == _deviceId)) {
        _updateState(DeviceTransportState.disconnected);
        throw Exception('Ray-Ban Meta microphone not available over Bluetooth');
      }
      _updateState(DeviceTransportState.connected);
    } catch (e) {
      _updateState(DeviceTransportState.disconnected);
      rethrow;
    }
  }

  @override
  Future<void> disconnect() async {
    if (_state == DeviceTransportState.disconnected) {
      return;
    }

    _updateState(DeviceTransportState.disconnecting);

    await _runNativeTeardownStep(label: 'stopping audio during disconnect', action: _hostAPI.stopAudioCapture);
    await _runNativeTeardownStep(label: 'stopping camera during disconnect', action: _hostAPI.stopCamera);
    await _runNativeTeardownStep(label: 'disconnecting native session', action: _hostAPI.disconnect);

    for (final controller in _streamControllers.values) {
      _audioControllers.remove(controller);
      _photoControllers.remove(controller);
      await controller.close();
    }
    _streamControllers.clear();

    _updateState(DeviceTransportState.disconnected);
  }

  Future<void> _runNativeTeardownStep({required String label, required Future<void> Function() action}) async {
    try {
      await action();
    } catch (e) {
      Logger.debug('RayBanMeta Transport: Error $label: $e');
    }
  }

  @override
  Future<bool> isConnected() async {
    try {
      final mode = await _hostAPI.getAvailabilityMode();
      if (mode == 'full') {
        return await _hostAPI.getConnectionState() == 'connected';
      }
      if (mode == 'audio_only') {
        final inputs = await _hostAPI.getBluetoothHfpInputs();
        return inputs.any((input) => input.uid == _deviceId);
      }
      return false;
    } catch (e) {
      return false;
    }
  }

  @override
  Future<bool> ping() async {
    return await isConnected();
  }

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    if (serviceUuid == 'rayban-meta-audio-service' && characteristicUuid == 'rayban-meta-audio-data') {
      return _getAudioStream();
    } else if (serviceUuid == 'rayban-meta-camera-service' && characteristicUuid == 'rayban-meta-photo-data') {
      return _getPhotoStream();
    }

    return const Stream.empty();
  }

  Stream<List<int>> _getAudioStream() {
    const key = 'audio';

    if (!_streamControllers.containsKey(key)) {
      _streamControllers[key] = StreamController<List<int>>.broadcast();
      _audioControllers.add(_streamControllers[key]!);
    }

    return _streamControllers[key]!.stream;
  }

  Stream<List<int>> _getPhotoStream() {
    const key = 'photo';

    if (!_streamControllers.containsKey(key)) {
      _streamControllers[key] = StreamController<List<int>>.broadcast();
      _photoControllers.add(_streamControllers[key]!);
    }

    return _streamControllers[key]!.stream;
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    return [];
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {}

  Future<String> getAvailabilityMode() async {
    try {
      return await _hostAPI.getAvailabilityMode();
    } catch (e) {
      Logger.debug('RayBanMeta Transport: Error reading availability mode: $e');
      return 'none';
    }
  }

  Future<void> startAudioCapture() async {
    try {
      final mode = await _hostAPI.getAvailabilityMode();
      await _hostAPI.startAudioCapture(mode == 'audio_only' ? _deviceId : null);
    } catch (e) {
      Logger.debug('RayBanMeta Transport: Error starting audio capture: $e');
      rethrow;
    }
  }

  Future<void> stopAudioCapture() async {
    try {
      await _hostAPI.stopAudioCapture();
    } catch (e) {
      Logger.debug('RayBanMeta Transport: Error stopping audio capture: $e');
    }
  }

  Future<void> startCamera() async {
    try {
      await _hostAPI.startCamera();
    } catch (e) {
      Logger.debug('RayBanMeta Transport: Error starting camera: $e');
      rethrow;
    }
  }

  Future<void> stopCamera() async {
    try {
      await _hostAPI.stopCamera();
    } catch (e) {
      Logger.debug('RayBanMeta Transport: Error stopping camera: $e');
    }
  }

  Future<void> capturePhoto() async {
    try {
      await _hostAPI.capturePhoto();
    } catch (e) {
      Logger.debug('RayBanMeta Transport: Error capturing photo: $e');
      rethrow;
    }
  }

  Future<String> getCameraPermissionStatus() async {
    try {
      return await _hostAPI.getCameraPermissionStatus();
    } catch (e) {
      return 'unavailable';
    }
  }

  Future<String> requestCameraPermission() async {
    try {
      return await _hostAPI.requestCameraPermission();
    } catch (e) {
      Logger.debug('RayBanMeta Transport: Error requesting camera permission: $e');
      return 'denied';
    }
  }

  Future<bool> isGlassesAudioRouteActive() async {
    try {
      return await _hostAPI.isGlassesAudioRouteActive();
    } catch (e) {
      return false;
    }
  }

  @override
  Future<void> dispose() async {
    _instances.remove(this);

    for (final controller in _streamControllers.values) {
      _audioControllers.remove(controller);
      _photoControllers.remove(controller);
      await controller.close();
    }
    _streamControllers.clear();

    await _connectionStateController.close();
  }
}
