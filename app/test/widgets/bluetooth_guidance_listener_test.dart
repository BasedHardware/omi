import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/widgets/bluetooth_guidance_listener.dart';

void main() {
  testWidgets('shows one actionable dialog when a BLE operation is blocked by adapter power', (tester) async {
    final readiness = BluetoothReadiness(readState: () async => 'off', observeBridge: false);
    final navigatorKey = GlobalKey<NavigatorState>();

    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: navigatorKey,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) => BluetoothGuidanceListener(
          readiness: readiness,
          navigatorKey: navigatorKey,
          child: child!,
        ),
        home: const Scaffold(body: SizedBox()),
      ),
    );

    expect(await readiness.ensureReady(BluetoothUse.discovery), isFalse);
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text('Enable Bluetooth'), findsOneWidget);
    expect(find.text('Omi needs Bluetooth to connect to your wearable. Please enable Bluetooth and try again.'),
        findsOneWidget);

    await tester.tap(find.text('Ok'));
    await tester.pumpAndSettle();

    expect(readiness.guidance, isNull);
  });

  testWidgets('Android enable action refreshes readiness and retries the blocked operation', (tester) async {
    var nativeState = 'off';
    var retriedUse = <BluetoothUse>[];
    final readiness = BluetoothReadiness(
      readState: () async => nativeState,
      requestEnable: () async {
        nativeState = 'on';
        return true;
      },
      observeBridge: false,
    );

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: BluetoothGuidanceListener(
          readiness: readiness,
          isAndroid: true,
          retryBlockedOperation: (use) async => retriedUse.add(use),
          child: const Scaffold(body: SizedBox()),
        ),
      ),
    );

    expect(await readiness.ensureReady(BluetoothUse.discovery), isFalse);
    await tester.pumpAndSettle();
    expect(find.widgetWithText(TextButton, 'Enable Bluetooth'), findsOneWidget);

    await tester.tap(find.widgetWithText(TextButton, 'Enable Bluetooth'));
    await tester.pumpAndSettle();

    expect(readiness.state, BluetoothAdapterState.on);
    expect(retriedUse, [BluetoothUse.discovery]);
  });

  testWidgets('sends revoked Bluetooth permission to Settings instead of the adapter-enable flow', (tester) async {
    final readiness = BluetoothReadiness(
      readState: () async => 'on',
      permissionState: (_) async => BluetoothAdapterState.unauthorized,
      observeBridge: false,
    );

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: BluetoothGuidanceListener(readiness: readiness, child: const Scaffold(body: SizedBox())),
      ),
    );

    expect(await readiness.ensureReady(BluetoothUse.connection), isFalse);
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text('Permissions Required'), findsOneWidget);
    expect(find.text('Open Settings'), findsOneWidget);
  });
}
