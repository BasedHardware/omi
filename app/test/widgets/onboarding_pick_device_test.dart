import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/onboarding/pick_device_step.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';

/// Rev 3 onboarding: "What will you wear?" first, then the three-step Connect.
class _QuietOnboardingProvider extends OnboardingProvider {
  _QuietOnboardingProvider({bool connected = false}) {
    deviceList = [];
    isConnected = connected;
  }

  @override
  Future<void> scanDevices({required VoidCallback onShowDialog, VoidCallback? onShowLocationDialog}) async {}
}

/// Connect asks the device provider to reconnect a known device; nothing to reconnect here.
class _IdleDeviceProvider extends ChangeNotifier implements DeviceProvider {
  @override
  Future<void> initiateConnection(String source, {bool boundDeviceOnly = false}) async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _NoSpeakerCheckHomeProvider extends HomeProvider {
  @override
  Future setupHasSpeakerProfile() async {}
}

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Widget app(Widget home, {OnboardingProvider? onboarding}) => MultiProvider(
        providers: [
          ChangeNotifierProvider<OnboardingProvider>.value(value: onboarding ?? _QuietOnboardingProvider()),
          ChangeNotifierProvider<HomeProvider>(create: (_) => _NoSpeakerCheckHomeProvider()),
          ChangeNotifierProvider<DeviceProvider>(create: (_) => _IdleDeviceProvider()),
        ],
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          builder: (context, child) =>
              MediaQuery(data: MediaQuery.of(context).copyWith(disableAnimations: true), child: child!),
          home: home,
        ),
      );

  // The scanning ripple on Connect never settles; step through the page transition instead.
  Future<void> settleRoute(WidgetTester tester) async {
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
  }

  group('OnboardingPickDeviceStep', () {
    testWidgets('asks what you will wear; this phone moves on straight away', (tester) async {
      var next = 0;
      await tester.pumpWidget(app(Scaffold(body: OnboardingPickDeviceStep(goNext: () => next++))));
      expect(find.text('What will you wear?'), findsOneWidget);
      expect(find.byKey(const Key('add_device_omi')), findsOneWidget);

      await tester.scrollUntilVisible(find.byKey(const Key('add_device_phone')), 200,
          scrollable: find.byType(Scrollable).first);
      await tester.tap(find.byKey(const Key('add_device_phone')));
      await tester.pump();
      expect(next, 1);
    });

    testWidgets('a wearable opens Connect; Set up later comes back and moves on', (tester) async {
      var next = 0;
      await tester.pumpWidget(app(Scaffold(body: OnboardingPickDeviceStep(goNext: () => next++))));
      await tester.tap(find.byKey(const Key('add_device_omi')));
      await settleRoute(tester);
      expect(find.byType(ConnectDevicePage), findsOneWidget);
      expect(next, 0);

      await tester.tap(find.byKey(const Key('connect_set_up_later')));
      await settleRoute(tester);
      expect(find.byType(ConnectDevicePage), findsNothing);
      expect(next, 1);
    });

    testWidgets('backing out of Connect stays on the question', (tester) async {
      var next = 0;
      await tester.pumpWidget(app(Scaffold(body: OnboardingPickDeviceStep(goNext: () => next++))));
      await tester.tap(find.byKey(const Key('add_device_omi')));
      await settleRoute(tester);
      await tester.pageBack();
      await settleRoute(tester);
      expect(find.text('What will you wear?'), findsOneWidget);
      expect(next, 0);
    });
  });

  group('ConnectDevicePage in onboarding', () {
    testWidgets('Continue waits for the device; Set up later is always there', (tester) async {
      var done = 0;
      await tester.pumpWidget(app(ConnectDevicePage(onDone: () => done++)));
      await tester.pump();
      final continueButton = find.byKey(const Key('connect_continue'));
      expect(continueButton, findsOneWidget);
      await tester.tap(continueButton);
      expect(done, 0);
      await tester.tap(find.byKey(const Key('connect_set_up_later')));
      expect(done, 1);
    });

    testWidgets('a connected device enables Continue', (tester) async {
      var done = 0;
      await tester.pumpWidget(
          app(ConnectDevicePage(onDone: () => done++), onboarding: _QuietOnboardingProvider(connected: true)));
      await tester.pump();
      await tester.tap(find.byKey(const Key('connect_continue')));
      expect(done, 1);
    });
  });

  group('ConnectSteps', () {
    Widget steps({bool found = false, bool bluetooth = false, bool connected = false, String heard = ''}) =>
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: ConnectSteps(found: found, bluetoothAllowed: bluetooth, connected: connected, heard: heard),
          ),
        );

    testWidgets('three numbered steps, ticked as they happen', (tester) async {
      await tester.pumpWidget(steps());
      expect(find.text('Turn it on and hold it close'), findsOneWidget);
      expect(find.text('Allow Bluetooth'), findsOneWidget);
      expect(find.text('Say something to test'), findsOneWidget);
      expect(find.text('1'), findsOneWidget);
      expect(find.byIcon(Icons.check_rounded), findsNothing);

      await tester.pumpWidget(steps(found: true, bluetooth: true, connected: true));
      expect(find.byIcon(Icons.check_rounded), findsNWidgets(2));
      expect(find.text('Words appear here as you speak'), findsOneWidget);
    });

    testWidgets('the test shows the words the device heard', (tester) async {
      await tester.pumpWidget(steps(found: true, bluetooth: true, connected: true, heard: 'testing one two'));
      expect(find.text('“testing one two”'), findsOneWidget);
      expect(find.byIcon(Icons.check_rounded), findsNWidgets(3));
      final semantics = tester.ensureSemantics();
      expect(
        tester.getSemantics(find.text('Say something to test')),
        isSemantics(hasCheckedState: true, isChecked: true),
      );
      semantics.dispose();
    });
  });
}
