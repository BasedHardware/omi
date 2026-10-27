import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/devices.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final reconnectConfigurations = <Object?>[];
  setUp(() async {
    reconnectConfigurations.clear();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(
      'dev.flutter.pigeon.omi_pigeon.BleHostApi.configureSavedReconnect',
      (message) async {
        reconnectConfigurations.add(BleHostApi.pigeonChannelCodec.decodeMessage(message));
        return BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>[null]);
      },
    );
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(
      'dev.flutter.pigeon.omi_pigeon.BleHostApi.unmanageDevice',
      (_) async => BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>[null]),
    );
  });
  tearDown(() {
    for (final method in ['configureSavedReconnect', 'unmanageDevice']) {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(
        'dev.flutter.pigeon.omi_pigeon.BleHostApi.$method',
        null,
      );
    }
  });
  test('ensureConnection is blocked while stale bond recovery is required', () async {
    final service = DeviceService(connectionBuilder: (_) => null);
    service.requireStaleBondRecovery();

    final result = await service.ensureConnection('AA:BB:CC:DD:EE:FF', force: true);

    expect(result, isNull);
  });

  test('forgetDevice clears stale bond recovery requirement', () async {
    final service = DeviceService(connectionBuilder: (_) => null);
    service.requireStaleBondRecovery();

    await service.forgetDevice('AA:BB:CC:DD:EE:FF');

    expect(reconnectConfigurations, <Object?>[
      <Object?>['AA:BB:CC:DD:EE:FF', false],
    ]);
    expect(service.staleBondRecoveryRequired, isFalse);
  });
}
