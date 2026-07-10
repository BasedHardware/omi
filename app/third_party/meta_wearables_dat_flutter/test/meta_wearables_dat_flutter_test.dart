import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';
import 'package:meta_wearables_dat_flutter/src/meta_wearables_dat_method_channel.dart';
import 'package:meta_wearables_dat_flutter/src/meta_wearables_dat_platform_interface.dart';
import 'package:plugin_platform_interface/plugin_platform_interface.dart';

class _UnoverriddenPlatform extends MetaWearablesDatPlatform with MockPlatformInterfaceMixin {}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('models', () {
    test('DeviceInfo can be constructed and round-tripped through fromMap', () {
      const direct = DeviceInfo(
        uuid: 'abc',
        name: 'Ray-Ban Meta',
        kind: DeviceKind.rayBanMeta,
      );
      expect(direct.uuid, 'abc');
      expect(direct.kind, DeviceKind.rayBanMeta);

      final parsed = DeviceInfo.fromMap(<Object?, Object?>{
        'uuid': 'abc',
        'name': 'Ray-Ban Meta',
        'kind': 'rayBanMeta',
      });
      expect(parsed.uuid, 'abc');
      expect(parsed.kind, DeviceKind.rayBanMeta);
    });

    test('Enums map cleanly to and from platform-channel ints / strings', () {
      expect(RegistrationState.fromInt(3), RegistrationState.registered);
      expect(StreamSessionState.fromInt(3), StreamSessionState.streaming);
      expect(DeviceSessionState.fromInt(2), DeviceSessionState.started);
      expect(DeviceSessionState.fromInt(5), DeviceSessionState.stopped);
      expect(StreamQuality.high.width, 720);
      expect(StreamQuality.high.height, 1280);
      expect(StreamQuality.fpsValues, contains(30));
      expect(DeviceKind.fromRaw('unknown_value'), DeviceKind.unknown);
      expect(CameraFacing.front.value, 'front');
      expect(MockPermission.camera.value, 'camera');
      expect(MockPermissionStatus.granted.value, 'granted');
    });

    test('DatError subclasses preserve code and message', () {
      const err = SessionError(code: 'X', message: 'boom');
      expect(err, isA<DatError>());
      expect(err.code, 'X');
      expect(err.toString(), contains('SessionError'));
      expect(err.toString(), contains('boom'));
    });

    test('SessionError is* getters key off typed sub-codes', () {
      const thermal = SessionError(
        code: DatErrorCodes.thermalCritical,
        message: 'too hot',
      );
      expect(thermal.isThermalCritical, isTrue);
      expect(thermal.isHingesClosed, isFalse);
      expect(thermal.isPermissionDenied, isFalse);
      expect(thermal.isDeviceDisconnected, isFalse);

      const hinges = SessionError(
        code: DatErrorCodes.hingesClosed,
        message: 'hinges',
      );
      expect(hinges.isHingesClosed, isTrue);
      expect(hinges.isThermalCritical, isFalse);
    });

    test('CaptureError is* getters key off typed sub-codes', () {
      const inflight = CaptureError(
        code: DatErrorCodes.captureInProgress,
        message: 'already capturing',
      );
      expect(inflight.isCaptureInProgress, isTrue);
      expect(inflight.isDeviceDisconnected, isFalse);
      expect(inflight.isCaptureFailed, isFalse);
      expect(inflight.isNotStreaming, isFalse);
    });

    test('RegistrationError is* getters key off typed sub-codes', () {
      const config = RegistrationError(
        code: DatErrorCodes.configurationInvalid,
        message: 'missing MWDAT',
      );
      expect(config.isConfigurationInvalid, isTrue);
      expect(config.isMetaAiNotInstalled, isFalse);
      expect(config.isAlreadyRegistered, isFalse);

      const noMetaAi = RegistrationError(
        code: DatErrorCodes.metaAiNotInstalled,
        message: 'no Meta AI',
      );
      expect(noMetaAi.isMetaAiNotInstalled, isTrue);
      expect(noMetaAi.isConfigurationInvalid, isFalse);
    });

    test('DeviceSessionError is* getters key off typed sub-codes', () {
      const noDevice = DeviceSessionError(
        code: DatErrorCodes.noEligibleDevice,
        message: 'no glasses',
      );
      expect(noDevice.isNoEligibleDevice, isTrue);
      expect(noDevice.isUnexpectedError, isFalse);

      const exists = DeviceSessionError(
        code: DatErrorCodes.sessionAlreadyExists,
        message: 'already exists',
      );
      expect(exists.isSessionAlreadyExists, isTrue);
      expect(exists.isNoEligibleDevice, isFalse);
    });

    test('FrameData and PhotoResult hold their bytes', () {
      final frame = FrameData(
        bytes: Uint8List.fromList([1, 2, 3]),
        width: 4,
        height: 4,
        format: FrameFormat.rawRgba,
      );
      expect(frame.bytes.length, 3);
      expect(frame.format, FrameFormat.rawRgba);

      final photo = PhotoResult(
        bytes: Uint8List.fromList([0xff, 0xd8]),
        format: PhotoFormat.jpeg,
      );
      expect(photo.format, PhotoFormat.jpeg);
    });

    test('VideoStreamSize parses platform-channel maps', () {
      final size = VideoStreamSize.fromMap(<Object?, Object?>{
        'width': 720,
        'height': 1280,
      });
      expect(size.width, 720);
      expect(size.height, 1280);
      expect(size.toString(), 'VideoStreamSize(720x1280)');
    });

    test('VideoFrame parses raw + hvc1 platform-channel maps', () {
      final raw = VideoFrame.fromMap(<Object?, Object?>{
        'codec': 'raw',
        'bytes': Uint8List.fromList([1, 2, 3, 4]),
        'width': 1280,
        'height': 720,
        'ptsUs': 33333,
        'isKeyframe': true,
        'bytesPerRow': 5120,
      });
      expect(raw.codec, VideoCodec.raw);
      expect(raw.bytes.length, 4);
      expect(raw.width, 1280);
      expect(raw.height, 720);
      expect(raw.ptsUs, 33333);
      expect(raw.isKeyframe, isTrue);
      expect(raw.bytesPerRow, 5120);

      final hvc1 = VideoFrame.fromMap(<Object?, Object?>{
        'codec': 'hvc1',
        'bytes': <int>[0, 0, 0, 1, 0x40],
        'width': 1280,
        'height': 720,
        'ptsUs': 66666,
        'isKeyframe': false,
      });
      expect(hvc1.codec, VideoCodec.hvc1);
      expect(hvc1.bytes.length, 5);
      expect(hvc1.isKeyframe, isFalse);
      expect(hvc1.bytesPerRow, isNull);
    });

    test('BackgroundNotification serialises through toMap()', () {
      const notif = BackgroundNotification(
        title: 'Streaming',
        text: 'Stay open',
        channelId: 'ch',
        channelName: 'Channel',
        iconResourceName: 'ic_stream',
      );
      final map = notif.toMap();
      expect(map['title'], 'Streaming');
      expect(map['text'], 'Stay open');
      expect(map['channelId'], 'ch');
      expect(map['channelName'], 'Channel');
      expect(map['iconResourceName'], 'ic_stream');

      const minimal = BackgroundNotification(
        title: 't',
        text: 'b',
        channelId: 'c',
        channelName: 'C',
      );
      final minimalMap = minimal.toMap();
      expect(minimalMap.containsKey('iconResourceName'), isFalse);
    });

    test('DeviceCompatibility maps wire strings to enum cases', () {
      expect(
        DeviceCompatibility.fromRaw('compatible'),
        DeviceCompatibility.compatible,
      );
      expect(
        DeviceCompatibility.fromRaw('deviceUpdateRequired'),
        DeviceCompatibility.deviceUpdateRequired,
      );
      expect(
        DeviceCompatibility.fromRaw('sdkUpdateRequired'),
        DeviceCompatibility.sdkUpdateRequired,
      );
      expect(
        DeviceCompatibility.fromRaw('garbage'),
        DeviceCompatibility.unknown,
      );

      final event = DeviceCompatibilityEvent.fromMap(<Object?, Object?>{
        'deviceUuid': 'aaaa-bbbb',
        'compatibility': 'compatible',
      });
      expect(event.deviceUuid, 'aaaa-bbbb');
      expect(event.compatibility, DeviceCompatibility.compatible);
    });
  });

  group('platform interface', () {
    test('default instance is the MethodChannel implementation', () {
      expect(
        MetaWearablesDatPlatform.instance,
        isInstanceOf<MethodChannelMetaWearablesDat>(),
      );
    });

    test('unimplemented members throw UnimplementedError', () {
      MetaWearablesDatPlatform.instance = _UnoverriddenPlatform();
      addTearDown(() {
        MetaWearablesDatPlatform.instance = MethodChannelMetaWearablesDat();
      });

      expect(
        MetaWearablesDat.requestAndroidPermissions,
        throwsA(isA<UnimplementedError>()),
      );
      expect(
        MetaWearablesDat.startRegistration,
        throwsA(isA<UnimplementedError>()),
      );
      expect(
        () => MetaWearablesDat.handleUrl('x'),
        throwsA(isA<UnimplementedError>()),
      );
      expect(
        MetaWearablesDat.startUnregistration,
        throwsA(isA<UnimplementedError>()),
      );
      expect(
        MetaWearablesDat.startStreamSession,
        throwsA(isA<UnimplementedError>()),
      );
      expect(
        MetaWearablesDat.capturePhoto,
        throwsA(isA<UnimplementedError>()),
      );
      expect(
        MetaWearablesDat.enableMockDevice,
        throwsA(isA<UnimplementedError>()),
      );
      expect(
        MetaWearablesDat.enableBackgroundStreaming,
        throwsA(isA<UnimplementedError>()),
      );
      expect(
        MetaWearablesDat.disableBackgroundStreaming,
        throwsA(isA<UnimplementedError>()),
      );
      expect(
        MetaWearablesDat.getDevices,
        throwsA(isA<UnimplementedError>()),
      );
      expect(
        MetaWearablesDat.videoFramesStream,
        throwsA(isA<UnimplementedError>()),
      );
    });

    test('fake platform implementation drives every facade method', () async {
      final fake = _FakePlatform();
      MetaWearablesDatPlatform.instance = fake;
      addTearDown(() {
        MetaWearablesDatPlatform.instance = MethodChannelMetaWearablesDat();
      });

      expect(await MetaWearablesDat.getPlatformVersion(), 'fake 1.2.3');
      expect(await MetaWearablesDat.requestAndroidPermissions(), isTrue);
      await MetaWearablesDat.startRegistration();
      expect(await MetaWearablesDat.handleUrl('mywearables://callback'), isTrue);
      expect(
        (await MetaWearablesDat.getDevices()).first.uuid,
        'mock-device',
      );

      // Mock kit
      await MetaWearablesDat.enableMockDevice();
      final uuid = await MetaWearablesDat.pairMockRayBanMeta();
      expect(uuid, 'mock-uuid');
      await MetaWearablesDat.setMockPermission(
        MockPermission.camera,
        MockPermissionStatus.granted,
      );

      // Streaming
      final id = await MetaWearablesDat.startStreamSession(
        deviceKinds: {DeviceKind.rayBanMeta},
        videoCodec: VideoCodec.hvc1,
      );
      expect(id, 42);
      expect(fake.lastDeviceKinds, {DeviceKind.rayBanMeta});
      expect(fake.lastVideoCodec, VideoCodec.hvc1);

      // Background streaming
      await MetaWearablesDat.enableBackgroundStreaming(
        androidNotification: const BackgroundNotification(
          title: 't',
          text: 'b',
          channelId: 'c',
          channelName: 'C',
        ),
      );
      expect(fake.backgroundEnabled, isTrue);
      await MetaWearablesDat.disableBackgroundStreaming();
      expect(fake.backgroundEnabled, isFalse);

      // Streams
      expect(
        await MetaWearablesDat.devicesStream().first,
        hasLength(1),
      );
      expect(
        (await MetaWearablesDat.compatibilityStream().first).compatibility,
        DeviceCompatibility.compatible,
      );
      expect(
        (await MetaWearablesDat.videoFramesStream().first).codec,
        VideoCodec.raw,
      );
    });
  });
}

/// Fake [MetaWearablesDatPlatform] used to make sure the facade plumbing
/// (every static method delegates to the instance, the argument bag is
/// forwarded faithfully) actually works without spinning up a platform
/// channel. Mirrors the "mock-platform test" mentioned in the v0.1 plan.
class _FakePlatform extends MetaWearablesDatPlatform with MockPlatformInterfaceMixin {
  Set<DeviceKind>? lastDeviceKinds;
  VideoCodec? lastVideoCodec;
  bool backgroundEnabled = false;

  @override
  Future<String?> getPlatformVersion() async => 'fake 1.2.3';

  @override
  Future<bool> requestAndroidPermissions() async => true;

  @override
  Future<void> startRegistration({String? appId, String? urlScheme}) async {}

  @override
  Future<bool> handleUrl(String url) async => true;

  @override
  Future<List<DeviceInfo>> getDevices() async => const [
        DeviceInfo(
          uuid: 'mock-device',
          name: 'Mock',
          kind: DeviceKind.rayBanMeta,
        ),
      ];

  @override
  Stream<List<DeviceInfo>> devicesStream() => Stream.value(const [
        DeviceInfo(
          uuid: 'mock-device',
          name: 'Mock',
          kind: DeviceKind.rayBanMeta,
        ),
      ]);

  @override
  Stream<DeviceCompatibilityEvent> compatibilityStream() => Stream.value(
        const DeviceCompatibilityEvent(
          deviceUuid: 'mock-device',
          compatibility: DeviceCompatibility.compatible,
        ),
      );

  @override
  Stream<VideoFrame> videoFramesStream() => Stream.value(
        VideoFrame(
          codec: VideoCodec.raw,
          bytes: Uint8List(0),
          width: 1280,
          height: 720,
          ptsUs: 0,
          isKeyframe: true,
          bytesPerRow: 5120,
        ),
      );

  @override
  Future<void> enableMockDevice({
    bool initiallyRegistered = true,
    bool initialPermissionsGranted = true,
  }) async {}

  @override
  Future<String> pairMockRayBanMeta() async => 'mock-uuid';

  @override
  Future<void> setMockPermission(String permission, String status) async {}

  @override
  Future<int> startStreamSession({
    String? deviceUUID,
    int fps = 30,
    StreamQuality quality = StreamQuality.medium,
    Set<DeviceKind>? deviceKinds,
    VideoCodec videoCodec = VideoCodec.raw,
  }) async {
    lastDeviceKinds = deviceKinds;
    lastVideoCodec = videoCodec;
    return 42;
  }

  @override
  Future<void> enableBackgroundStreaming({
    BackgroundNotification? androidNotification,
  }) async {
    backgroundEnabled = true;
  }

  @override
  Future<void> disableBackgroundStreaming() async {
    backgroundEnabled = false;
  }
}
