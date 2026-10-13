import 'dart:async';

import 'package:flutter/material.dart';
import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/connect_omi/connect_omi_step.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/services/services.dart';

/// The shared pairing provider with the radio calls replaced: records what the step asks of it.
class _FakeOnboarding extends OnboardingProvider {
  int scans = 0;
  int cancels = 0;

  @override
  Future<void> scanDevices({required VoidCallback onShowDialog, VoidCallback? onShowLocationDialog}) async {
    scans++;
  }

  @override
  void cancelActiveScan() => cancels++;
}

class _FakeDevice extends DeviceProvider {
  _FakeDevice() : super(chargingConnectionLoader: (_) async => null);

  @override
  Future<void> initiateConnection(String caller, {bool boundDeviceOnly = false}) async {}
}

class _NoConnectivity extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

void main() {
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _NoConnectivity();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Already initialised by another test in this isolate.
    }
  });

  // The providers are app-wide singletons in production: hand them in by value so the test owns
  // their lifetime, as the app does.
  Future<void> pump(WidgetTester tester, _FakeOnboarding onboarding,
      {required void Function(OnboardingDeviceChoice) onDone,
      Future<void> Function(BuildContext, {required String source})? openShop}) {
    return tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<DeviceProvider>.value(value: _FakeDevice()),
          ChangeNotifierProvider<OnboardingProvider>.value(value: onboarding),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Scaffold(
            body:
                openShop == null ? ConnectOmiStep(onDone: onDone) : ConnectOmiStep(onDone: onDone, openShop: openShop),
          ),
        ),
      ),
    );
  }

  testWidgets('says "Connect Omi" and searches only after the arrival has played', (tester) async {
    final onboarding = _FakeOnboarding();
    await pump(tester, onboarding, onDone: (_) {});

    expect(find.text('Connect Omi'), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 500));
    expect(onboarding.scans, 0, reason: 'no Bluetooth guidance may cover the arrival');
    await tester.pump(const Duration(seconds: 2)); // The search rings never settle.
    expect(onboarding.scans, 1);
  });

  testWidgets('"I\'ve ordered mine" leaves once with that answer', (tester) async {
    final choices = <OnboardingDeviceChoice>[];
    await pump(tester, _FakeOnboarding(), onDone: choices.add);
    await tester.pump(const Duration(seconds: 2)); // The search rings never settle.

    await tester.tap(find.byKey(const Key('connect_omi_ordered')));
    await tester.tap(find.byKey(const Key('connect_omi_ordered')), warnIfMissed: false);
    await tester.pump();

    expect(choices, [OnboardingDeviceChoice.ordered]);
  });

  testWidgets('"Not ordered yet" opens the Omi store, and onboarding carries on once it is closed', (tester) async {
    final choices = <OnboardingDeviceChoice>[];
    final sources = <String>[];
    final closed = Completer<void>();
    await pump(
      tester,
      _FakeOnboarding(),
      onDone: choices.add,
      openShop: (_, {required source}) {
        sources.add(source);
        return closed.future;
      },
    );
    await tester.pump(const Duration(seconds: 2));

    await tester.tap(find.byKey(const Key('connect_omi_not_ordered')));
    await tester.tap(find.byKey(const Key('connect_omi_not_ordered')), warnIfMissed: false);
    await tester.pump();
    expect(sources, ['onboarding_not_ordered'], reason: 'one store, tagged with where it came from');
    expect(choices, isEmpty, reason: 'still in the store');

    closed.complete();
    await tester.pump();
    expect(choices, [OnboardingDeviceChoice.notOrdered]);
  });

  testWidgets('a nearby device is shown as a row to connect', (tester) async {
    final device = BtDevice(name: 'Omi', id: 'AA:BB', type: DeviceType.omi, rssi: -50);
    final onboarding = _FakeOnboarding()
      ..deviceList = [device]
      ..foundDevicesMap = {device.id: device};
    await pump(tester, onboarding, onDone: (_) {});
    await tester.pump(const Duration(seconds: 2)); // The search rings never settle.

    expect(find.text('Omi'), findsOneWidget);
    expect(find.text('1 DEVICE FOUND NEARBY'), findsOneWidget);
  });

  testWidgets('leaving stops the search and clears "nothing found" for the in-app pairing page', (tester) async {
    final onboarding = _FakeOnboarding();
    await pump(tester, onboarding, onDone: (_) {});
    await tester.pump(const Duration(seconds: 2)); // The search rings never settle.
    onboarding.enableInstructions = true; // The search came up empty here.

    await tester.pumpWidget(const SizedBox());

    expect(onboarding.cancels, greaterThan(0));
    expect(onboarding.enableInstructions, isFalse);
  });
}
