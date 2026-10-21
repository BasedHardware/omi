import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/devices.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(
      'dev.flutter.pigeon.omi_pigeon.BleHostApi.unmanageDevice',
      (_) async => BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>[null]),
    );
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

    expect(service.staleBondRecoveryRequired, isFalse);
  });
}
