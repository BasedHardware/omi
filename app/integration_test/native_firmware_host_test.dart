import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/home/firmware_update_dialog.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/utils/firmware_update_prompt_coordinator.dart';
import 'package:omi/widgets/confirmation_dialog.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';
import 'visual_audit/fakes.dart';

final _device = BtDevice(
    id: 'native-firmware-fixture',
    name: 'Omi Device',
    type: DeviceType.omi,
    rssi: -50,
    modelNumber: 'Omi',
    firmwareRevision: '2.0.10');

void main() => runNativeHostSuite((checkNativeHost) {
      testWidgets('native firmware update projects the available update from a stubbed version check', (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        PackageInfo.setMockInitialValues(
            appName: 'Omi', packageName: 'com.friend.ios', version: '1.0.0', buildNumber: '1', buildSignature: '');
        await tester.pumpWidget(nativeHostApp(
            FirmwareUpdate(
                device: _device,
                firmwareDetailsLoader: () async => {
                      'version': '3.0.1',
                      'min_version': '2.0.0',
                      'changelog': ['Faster sync', 'Longer battery life'],
                      'zip_url': 'https://firmware.invalid/omi.zip',
                      'ota_update_steps': ['no_usb', 'battery', 'internet'],
                    }),
            providers: [
              ChangeNotifierProvider<DeviceProvider>.value(
                  value: AuditDeviceProvider(connected: true, battery: 80, device: _device)),
            ]));
        await checkNativeHost(tester, 'native-firmware-ota-update-dark');
        expect(nativeProjectedRow(tester, 'fw_latest').subtitle, '3.0.1');
        expect(nativeProjectedRow(tester, 'fw_start').enabled, isTrue);
        await tester.pumpWidget(const SizedBox());
        await tester.pump();
      });

      testWidgets('the update-available prompt goes through the native presenter', (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        final coordinator = FirmwareUpdatePromptCoordinator()..setAvailableVersion('3.0.1');
        final prompt = coordinator.beginPresentation()!;
        final accepted = <NavigatorState>[];
        Future<void>? closed;
        await tester.pumpWidget(nativeHostApp(Builder(
            builder: (context) => Scaffold(
                body: Center(
                    child: TextButton(
                        onPressed: () => closed = presentFirmwareUpdatePrompt(context,
                            coordinator: coordinator, prompt: prompt, version: '3.0.1', onAccept: accepted.add),
                        child: const Text('open')))))));
        await tester.tap(find.text('open'));
        expect(closed, isNotNull);
        var done = false;
        unawaited(closed!.whenComplete(() => done = true));
        await tester.pump(const Duration(seconds: 2));
        await Future<void>.delayed(const Duration(seconds: 1));
        await tester.pump();
        expect(find.byType(ConfirmationDialog), findsNothing, reason: 'the native alert replaces the Flutter dialog');
        expect(done, isFalse, reason: 'the native alert is still presented');
        await captureNativeHostScreenshot('native-firmware-ota-prompt-dark');

        // The coordinator withdraws it: neither accepted nor deferred.
        coordinator.invalidatePresentation();
        await closed!.timeout(const Duration(seconds: 5));
        await tester.pump();
        expect(accepted, isEmpty);
        expect(coordinator.beginPresentation(), isNotNull);
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox());
        await tester.pump();
      });
    });
