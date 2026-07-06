import 'dart:async';
import 'dart:typed_data';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/discovery/rayban_meta_discoverer.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/rayban_meta_transport.dart';
import 'package:omi/utils/logger.dart';

const String rayBanMetaAudioServiceUuid = 'rayban-meta-audio-service';
const String rayBanMetaAudioDataCharacteristicUuid = 'rayban-meta-audio-data';
const String rayBanMetaCameraServiceUuid = 'rayban-meta-camera-service';
const String rayBanMetaPhotoDataCharacteristicUuid = 'rayban-meta-photo-data';

/// Ray-Ban Meta glasses as an Omi capture device.
///
/// Adapter over [RayBanMetaTransport]: audio arrives as PCM16 mono frames from
/// the glasses' Bluetooth HFP microphone, photos as JPEG bytes from the Meta
/// Wearables Device Access Toolkit camera. In the labeled audio-only fallback
/// (toolkit not in this build) every camera capability honestly reports
/// unavailable — no faked success.
class RayBanMetaDeviceConnection extends DeviceConnection {
  RayBanMetaDeviceConnection(super.device, super.transport);

  /// Interval between automatic photo captures while the photo controller is
  /// active — mirrors OmiGlass's periodic visual-context capture. The glasses'
  /// hardware capture LED stays on for the whole session, so capture state is
  /// always visible to bystanders.
  static const Duration autoCaptureInterval = Duration(seconds: 30);

  Timer? _autoCaptureTimer;

  RayBanMetaTransport get _metaTransport => transport as RayBanMetaTransport;

  bool get isAudioOnly => device.locator?.extras[RayBanMetaDiscoverer.audioOnlyExtraKey] == true;

  @override
  Future<void> connect({Function(String deviceId, DeviceConnectionState state)? onConnectionStateChanged}) async {
    await super.connect(onConnectionStateChanged: onConnectionStateChanged);
  }

  @override
  Future<bool> isConnected() async {
    return await transport.isConnected();
  }

  @override
  Future<void> disconnect() async {
    _autoCaptureTimer?.cancel();
    _autoCaptureTimer = null;
    await transport.disconnect();
    connectionState = DeviceConnectionState.disconnected;
  }

  /// The toolkit does not expose battery level (DAT 0.8), so report unknown.
  @override
  Future<int> performRetrieveBatteryLevel() async {
    return -1;
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetBleBatteryLevelListener({
    void Function(int p1)? onBatteryLevelChange,
  }) async {
    return null;
  }

  @override
  Future<StreamSubscription?> performGetBleAudioBytesListener({
    required void Function(List<int> p1) onAudioBytesReceived,
  }) async {
    final stream = transport.getCharacteristicStream(rayBanMetaAudioServiceUuid, rayBanMetaAudioDataCharacteristicUuid);

    final subscription = stream.listen((bytes) {
      onAudioBytesReceived(bytes);
    });

    // The glasses mic only flows once the HFP capture engine runs; start it
    // when the capture pipeline attaches, so listening state == capturing state.
    try {
      await _metaTransport.startAudioCapture();
    } catch (e) {
      Logger.debug('Ray-Ban Meta: failed to start audio capture: $e');
    }

    return subscription;
  }

  @override
  Future<BleAudioCodec> performGetAudioCodec() async {
    return BleAudioCodec.pcm16;
  }

  /// Whether the glasses' HFP mic is the active input route right now.
  Future<bool> isGlassesAudioRouteActive() => _metaTransport.isGlassesAudioRouteActive();

  Future<String> getCameraPermissionStatus() async {
    if (isAudioOnly) return 'unavailable';
    return _metaTransport.getCameraPermissionStatus();
  }

  Future<String> requestCameraPermission() async {
    if (isAudioOnly) return 'unavailable';
    return _metaTransport.requestCameraPermission();
  }

  /// Captures a single photo on demand; it arrives through the image listener.
  Future<void> capturePhoto() async {
    if (isAudioOnly) {
      throw DeviceConnectionException('Ray-Ban Meta audio-only mode has no camera access');
    }
    await _metaTransport.capturePhoto();
  }

  @override
  Future performCameraStartPhotoController() async {
    if (isAudioOnly) return null;
    try {
      await _metaTransport.startCamera();
      _autoCaptureTimer?.cancel();
      _autoCaptureTimer = Timer.periodic(autoCaptureInterval, (_) async {
        try {
          await _metaTransport.capturePhoto();
        } catch (e) {
          Logger.debug('Ray-Ban Meta: periodic photo capture failed: $e');
        }
      });
    } catch (e) {
      Logger.debug('Ray-Ban Meta: failed to start camera: $e');
    }
    return null;
  }

  @override
  Future performCameraStopPhotoController() async {
    if (isAudioOnly) return null;
    _autoCaptureTimer?.cancel();
    _autoCaptureTimer = null;
    await _metaTransport.stopCamera();
    return null;
  }

  @override
  Future<bool> performHasPhotoStreamingCharacteristic() async {
    if (isAudioOnly) return false;
    final mode = await _metaTransport.getAvailabilityMode();
    if (mode != 'full') return false;
    return await _metaTransport.getCameraPermissionStatus() == 'granted';
  }

  @override
  Future<StreamSubscription?> performGetImageListener({
    required void Function(OrientedImage orientedImage) onImageReceived,
  }) async {
    if (isAudioOnly) return null;

    final stream =
        transport.getCharacteristicStream(rayBanMetaCameraServiceUuid, rayBanMetaPhotoDataCharacteristicUuid);

    final subscription = stream.listen((framed) {
      if (framed.length < 2) return;
      // First byte carries orientation (0..3 == degrees/90), rest is JPEG.
      final orientation = ImageOrientation.fromValue(framed[0]);
      final jpegBytes = Uint8List.fromList(framed.sublist(1));
      onImageReceived(OrientedImage(imageBytes: jpegBytes, orientation: orientation));
    });

    return subscription;
  }

  @override
  Future<List<int>> performGetButtonState() async {
    return <int>[];
  }

  @override
  Future<StreamSubscription?> performGetBleButtonListener({
    required void Function(List<int> p1) onButtonReceived,
  }) async {
    return null;
  }

  @override
  Future<bool> performPlayToSpeakerHaptic(int mode) async {
    return false;
  }

  @override
  Future<List<int>> performGetStorageList() async {
    return <int>[];
  }

  @override
  Future<bool> performWriteToStorage(int numFile, int command, int offset) async {
    return false;
  }

  @override
  Future<StreamSubscription?> performGetBleStorageBytesListener({
    required void Function(List<int> p1) onStorageBytesReceived,
  }) async {
    return null;
  }

  @override
  Future<StreamSubscription<List<int>>?> performGetAccelListener({void Function(int p1)? onAccelChange}) async {
    return null;
  }

  @override
  Future<int> performGetFeatures() async {
    return 0;
  }

  @override
  Future<void> performSetLedDimRatio(int ratio) async {
    return;
  }

  @override
  Future<int?> performGetLedDimRatio() async {
    return null;
  }

  @override
  Future<void> performSetMicGain(int gain) async {
    return;
  }

  @override
  Future<int?> performGetMicGain() async {
    return null;
  }
}
