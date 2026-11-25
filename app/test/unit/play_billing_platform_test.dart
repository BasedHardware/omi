// The default Play platform must be the registered Android plugin: an unregistered
// InAppPurchasePlatform.instance throws on a real device and every price load fails.
import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:in_app_purchase_android/in_app_purchase_android.dart';
import 'package:in_app_purchase_platform_interface/in_app_purchase_platform_interface.dart';

import 'package:omi/services/billing/play_billing.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('the default platform registers the Android plugin on first use, through the real path', () async {
    final calls = <String>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(
      'dev.flutter.pigeon.in_app_purchase_android.InAppPurchaseApi.startConnection',
      (ByteData? message) async {
        calls.add('startConnection');
        return null; // no native Play side in a unit test
      },
    );
    expect(() => InAppPurchasePlatform.instance, throwsA(anything), reason: 'nothing registered at startup');
    final channelErrors = <Object>[];
    late InAppPurchasePlatform platform;
    await runZonedGuarded(() async {
      platform = PlayBilling.androidPlayPlatform();
      await Future<void>.delayed(Duration.zero);
    }, (error, _) => channelErrors.add(error));
    expect(platform, isA<InAppPurchaseAndroidPlatform>());
    expect(identical(InAppPurchasePlatform.instance, platform), isTrue);
    expect(identical(PlayBilling.androidPlayPlatform(), platform), isTrue, reason: 'registered once');
    expect(calls, contains('startConnection'), reason: 'the Android billing client connects only now, on first use');
    expect(channelErrors.every((e) => e is PlatformException), isTrue);
  });
}
