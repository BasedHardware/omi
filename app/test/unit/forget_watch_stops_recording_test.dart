import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/apple_watch_connection.dart';
import 'package:omi/services/devices/transports/watch_transport.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final watch = BtDevice(id: 'apple-watch', name: 'Apple Watch', type: DeviceType.appleWatch, rssi: 0);
  final mockedChannels = <String>{};
  late List<String> calls;
  late bool failStop;

  // The phone-side WatchConnectivity host, recording which calls reach the Watch.
  void mockWatchHost(String method, Object? reply) {
    final channel = 'dev.flutter.pigeon.omi_pigeon.WatchRecorderHostAPI.$method';
    mockedChannels.add(channel);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(channel, (_) async {
      calls.add(method);
      if (method == 'stopRecording' && failStop) {
        return WatchRecorderHostAPI.pigeonChannelCodec.encodeMessage(<Object?>['error', 'unreachable', null]);
      }
      return WatchRecorderHostAPI.pigeonChannelCodec.encodeMessage(<Object?>[reply]);
    });
  }

  setUp(() async {
    calls = [];
    failStop = false;
    for (final method in ['isWatchSessionSupported', 'isWatchPaired', 'isWatchReachable']) {
      mockWatchHost(method, true);
    }
    mockWatchHost('checkMainAppMicrophonePermission', true);
    mockWatchHost('getWatchInfo', <String, String>{'model': 'Apple Watch', 'systemVersion': 'test'});
    mockWatchHost('startRecording', null);
    mockWatchHost('stopRecording', null);
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    await SharedPreferencesUtil().btDeviceAdd(watch);
  });

  tearDown(() {
    for (final channel in mockedChannels) {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(channel, null);
    }
    mockedChannels.clear();
  });

  Future<(DeviceService, AppleWatchDeviceConnection)> recordingWatch() async {
    final connection = AppleWatchDeviceConnection(watch, WatchTransport());
    final service = DeviceService(connectionBuilder: (_) => connection);
    expect(await service.ensureConnection(watch.id, force: true), same(connection));
    expect(await connection.checkPermissionAndStartRecording(), isTrue);
    return (service, connection);
  }

  test('forgetting an Apple Watch stops its recording (#20780)', () async {
    final (service, _) = await recordingWatch();

    await service.forgetDevice(watch.id);

    expect(calls.where((c) => c == 'stopRecording'), hasLength(1));
    expect(calls.lastIndexOf('stopRecording'), greaterThan(calls.lastIndexOf('startRecording')));
    expect(service.connectionFor(watch.id), isNull);
  });

  test('a Watch that cannot be told to stop is still forgotten', () async {
    final (service, _) = await recordingWatch();
    failStop = true;

    await service.forgetDevice(watch.id);

    expect(calls, contains('stopRecording'));
    expect(service.connectionFor(watch.id), isNull);
  });

  test('disconnecting an Apple Watch does not stop its recording', () async {
    final (service, _) = await recordingWatch();

    await service.disconnectDevice(watch.id);

    expect(calls, isNot(contains('stopRecording')));
  });
}
