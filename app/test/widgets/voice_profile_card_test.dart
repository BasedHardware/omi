import 'package:flutter/material.dart';
import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/experiments/home_redesign.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/services/services.dart';

class _Device extends DeviceProvider {
  _Device() : super(chargingConnectionLoader: (_) async => null) {
    pairedDevice = BtDevice(id: 'p', name: 'Omi', type: DeviceType.omi, rssi: -40);
    isConnected = true;
  }

  @override
  Future<void> initiateConnection(String caller, {bool boundDeviceOnly = false}) async {}
}

class _NoConnectivity extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

// "Teach Omi your voice" shows only without a voice profile; closing it hides it for good and
// points to Settings > Voice Profile.
void main() {
  // These cover the redesigned Home (home-redesign test arm).
  setUp(() => HomeRedesign.setForTesting(true));
  tearDown(HomeRedesign.resetForTesting);

  setUpAll(() async {
    ConnectivityPlatform.instance = _NoConnectivity();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Already initialised by another test in this isolate.
    }
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<void> pump(WidgetTester tester, {required bool hasProfile}) {
    final home = HomeProvider()..hasSpeakerProfile = hasProfile;
    return tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<HomeProvider>.value(value: home),
          ChangeNotifierProvider<DeviceProvider>.value(value: _Device()),
        ],
        child: const MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: [Locale('en')],
          home: Scaffold(body: SpeechProfileCardWidget()),
        ),
      ),
    );
  }

  testWidgets('hidden once the reader has a voice profile', (tester) async {
    await pump(tester, hasProfile: true);
    expect(find.text('Teach Omi your voice'), findsNothing);
  });

  testWidgets('closing it hides it for good and points to Settings', (tester) async {
    await pump(tester, hasProfile: false);
    expect(find.text('Teach Omi your voice'), findsOneWidget);
    expect(find.bySemanticsLabel('Dismiss'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('voice_profile_card_dismiss')));
    await tester.pump();
    expect(find.text('Teach Omi your voice'), findsNothing);
    expect(find.text('You can set up Voice Profile anytime in Settings.'), findsOneWidget);
    expect(SharedPreferencesUtil().voiceProfileCardDismissed, isTrue);

    await tester.pumpWidget(const SizedBox());
    await pump(tester, hasProfile: false);
    expect(find.text('Teach Omi your voice'), findsNothing, reason: 'stays closed');
  });
}
