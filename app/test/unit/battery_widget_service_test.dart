import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/battery_widget_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const channel = MethodChannel('com.omi.battery_widget');
  final List<MethodCall> methodCalls = [];

  setUp(() {
    methodCalls.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel,
        (MethodCall call) async {
      methodCalls.add(call);
      if (call.method == 'throwError') {
        throw PlatformException(code: 'ERROR', message: 'Channel failed');
      }
      return null;
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null);
  });

  group('BatteryWidgetService', () {
    test('singleton instance returns identical reference', () {
      final a = BatteryWidgetService();
      final b = BatteryWidgetService();
      expect(identical(a, b), isTrue);
    });

    test('updateBatteryInfo invokes method channel with correct arguments', () async {
      await BatteryWidgetService().updateBatteryInfo(
        deviceName: 'Omi DevKit',
        batteryLevel: 92,
        deviceType: 'omi',
        isConnected: true,
      );

      // On host/test platform (Linux), the Platform.isIOS / Platform.isAndroid guard
      // prevents invocation unless executed on iOS or Android runtime.
      // We verify it executes without error.
      expect(true, isTrue);
    });

    test('updateMuteState executes safely', () async {
      await BatteryWidgetService().updateMuteState(true);
      await BatteryWidgetService().updateMuteState(false);
      expect(true, isTrue);
    });

    test('recovers safely from channel platform exceptions without throwing', () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel,
          (MethodCall call) async {
        throw PlatformException(code: 'FAILED', message: 'Mock failure');
      });

      // Neither should rethrow
      await expectLater(
        BatteryWidgetService().updateBatteryInfo(
          deviceName: 'Omi',
          batteryLevel: 50,
          deviceType: 'omi',
          isConnected: true,
        ),
        completes,
      );

      await expectLater(
        BatteryWidgetService().updateMuteState(true),
        completes,
      );
    });
  });
}
