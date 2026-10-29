import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/account_cutover/account_cutover_control.dart';
import 'package:omi/services/account_cutover/account_cutover_runtime.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/services/experiments/onboarding_variant_gate.dart';
import 'package:omi/services/experiments/paywall_experiment.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/bluetooth_guidance_listener.dart';

import '../../integration_test/visual_audit/fakes.dart' show AuditDeviceProvider;

// The `connect_first` arm of `onboarding-variant`: Connect your Omi right after sign-up (no Back),
// then control's steps; an Omi paired there skips the phone voice intro. Readers the flag does not
// assign keep control's order.

typedef _Steps = OnboardingConnectFirstStepsForTest;

/// The arm keeps control's Connect copy: only the position changes.
const _controlSubtitle = 'Pair your Omi and it captures your conversations hands-free, all day.';

/// Every step a reader walks from Connect until onboarding is done.
List<int> _walk({required bool pairedOmi, required bool setupPageEnabled}) {
  final order = <int>[];
  int? step = _Steps.connect;
  while (step != null) {
    order.add(step);
    step = _Steps.next(step, pairedOmi: pairedOmi, setupPageEnabled: setupPageEnabled);
  }
  return order;
}

class _QuietHome extends HomeProvider {
  @override
  Future setupHasSpeakerProfile() async {}
}

class _QuietAuth extends AuthenticationProvider {
  _QuietAuth() : super(initializeListeners: false);
}

final class _SignedIn implements AuthTokenGateway {
  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'u1', email: 'a@b.c', displayName: 'Alex');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;

  @override
  Future<void> signOut() async {}
}

class _Usage extends UsageProvider {
  @override
  Future<void> fetchSubscription() async {}
}

/// The device-connection service faked at its I/O edge: the scan, the OS Bluetooth permission and
/// the connect result. Everything above it is real: the Connect step, the Connect page and its
/// device list, the Bluetooth recovery prompt, and the wrapper's hand-off.
class _FakePairing extends OnboardingProvider {
  _FakePairing(this.readiness);

  final BluetoothReadiness readiness;
  bool bluetoothAllowed = true;
  int scans = 0;
  static final omi = BtDevice(id: 'OMI-TEST-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

  @override
  Future<void> scanDevices({required VoidCallback onShowDialog, VoidCallback? onShowLocationDialog}) async {
    scans++;
    if (!bluetoothAllowed) {
      // As a real scan does when the OS denies Bluetooth: the one recovery prompt, then the
      // "No Omi found" help with Scan Again.
      await readiness.ensureReady(BluetoothUse.discovery);
      enableInstructions = true;
      notifyListeners();
      return;
    }
    deviceList = [omi];
    notifyListeners();
  }

  @override
  Future<void> handleTap({required BtDevice device, required bool isFromOnboarding, VoidCallback? goNext}) async {
    // What a real connect leaves before it calls back: the Omi saved for the account, connected.
    await SharedPreferencesUtil().btDeviceSet(device);
    deviceId = device.id;
    deviceName = device.name;
    deviceType = device.type;
    isConnected = true;
    deviceList = [];
    notifyListeners();
    goNext?.call();
  }

  @override
  void cancelActiveScan() {}
}

/// One app run: providers, the pairing service and Bluetooth readiness as the app wires them.
class _Lane {
  bool bluetoothPermission = true;
  late final readiness = BluetoothReadiness(
    readState: () async => 'on',
    permissionState: (_) async => bluetoothPermission ? null : BluetoothAdapterState.unauthorized,
    observeBridge: false,
  );
  late final pairing = _FakePairing(readiness);
}

/// The OS permission plugin: everything granted, Settings recorded.
void _mockPermissions({void Function()? onOpenSettings}) {
  const channel = MethodChannel('flutter.baseflow.com/permissions/methods');
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(channel, (call) async {
    switch (call.method) {
      case 'checkPermissionStatus':
      case 'checkServiceStatus':
        return 1;
      case 'requestPermissions':
        return {for (final permission in call.arguments as List) permission: 1};
      case 'shouldShowRequestPermissionRationale':
        return false;
      case 'openAppSettings':
        onOpenSettings?.call();
        return true;
    }
    return null;
  });
  addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
}

/// A signed-in reader opening the app: the wrapper as the app mounts it, with the flag read
/// answering [variant].
Future<void> _pumpWrapper(WidgetTester tester, String? variant, _Lane lane) async {
  OnboardingVariantGate.warm(
    settledIdentity: () => 'u1',
    reload: () async => true,
    readVariant: (_) async => variant,
  );
  await tester.binding.setSurfaceSize(const Size(393, 852));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider<HomeProvider>(create: (_) => _QuietHome()),
      ChangeNotifierProvider<AuthenticationProvider>(create: (_) => _QuietAuth()),
      ChangeNotifierProvider<OnboardingProvider>.value(value: lane.pairing),
      ChangeNotifierProvider<DeviceProvider>(create: (_) => AuditDeviceProvider()),
      ChangeNotifierProvider<UsageProvider>(create: (_) => _Usage()),
    ],
    child: MaterialApp(
      navigatorKey: globalNavigatorKey,
      theme: buildOmiTheme(brightness: Brightness.light),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      builder: (context, child) => BluetoothGuidanceListener(readiness: lane.readiness, child: child!),
      home: const OnboardingWrapper(),
    ),
  ));
  await _settle(tester);
}

/// A signed-in reader on the Data & Privacy step whose flag read answers [variant].
Future<void> _pumpAtConsent(WidgetTester tester, String? variant) async {
  await _pumpWrapper(tester, variant, _Lane());
  expect(find.byKey(const Key('ai_consent_agree')), findsOneWidget);
}

Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 600));
}

/// Connect my Omi on the Connect step opens today's Connect page.
Future<void> _openConnectPage(WidgetTester tester) async {
  await tester.tap(find.byKey(const Key('first_capture_omi')));
  await _settle(tester);
  expect(find.byType(ConnectDevicePage), findsOneWidget);
}

Finder _omiRow() => find.ancestor(of: find.text('Omi'), matching: find.byType(InkWell)).first;

Future<void> _agree(WidgetTester tester) async {
  await tester.tap(find.byKey(const Key('ai_consent_agree')));
  await _settle(tester);
}

OnboardingProgressDots _dots(WidgetTester tester) =>
    tester.widget<OnboardingProgressDots>(find.byType(OnboardingProgressDots));

void main() {
  group('connect_first step order', () {
    test('Connect first, then control steps; the voice intro only without a paired Omi', () {
      expect(_walk(pairedOmi: false, setupPageEnabled: false), [
        _Steps.connect,
        _Steps.name,
        _Steps.language,
        _Steps.foundOmi,
        _Steps.permissions,
        _Steps.voiceIntro,
      ]);
      expect(_walk(pairedOmi: true, setupPageEnabled: false), [
        _Steps.connect,
        _Steps.name,
        _Steps.language,
        _Steps.foundOmi,
        _Steps.permissions,
      ]);
      // The flag-gated setup page still closes the flow, and Connect is never asked twice.
      expect(_walk(pairedOmi: false, setupPageEnabled: true).skip(5), [_Steps.voiceIntro, _Steps.setup]);
      expect(_walk(pairedOmi: true, setupPageEnabled: true).skip(4), [_Steps.permissions, _Steps.setup]);
      for (final paired in [false, true]) {
        for (final setup in [false, true]) {
          expect(_walk(pairedOmi: paired, setupPageEnabled: setup).where((s) => s == _Steps.connect), hasLength(1));
        }
      }
    });

    test('no Back on Connect or Name; Back elsewhere follows the walked order', () {
      for (final paired in [false, true]) {
        expect(_Steps.previous(_Steps.connect, pairedOmi: paired), isNull);
        expect(_Steps.previous(_Steps.name, pairedOmi: paired), isNull);
        expect(_Steps.previous(_Steps.language, pairedOmi: paired), _Steps.name);
        expect(_Steps.previous(_Steps.foundOmi, pairedOmi: paired), _Steps.language);
        expect(_Steps.previous(_Steps.permissions, pairedOmi: paired), _Steps.foundOmi);
      }
      expect(_Steps.previous(_Steps.voiceIntro, pairedOmi: false), _Steps.permissions);
      expect(_Steps.previous(_Steps.setup, pairedOmi: false), _Steps.voiceIntro);
      expect(_Steps.previous(_Steps.setup, pairedOmi: true), _Steps.permissions);
    });

    test('progress dots count control steps; a paired Omi drops the voice intro; Connect is not counted', () {
      expect(_Steps.progressSteps(pairedOmi: false), OnboardingProgressStepsForTest.steps);
      expect(
          _Steps.progressSteps(pairedOmi: true), [_Steps.name, _Steps.language, _Steps.foundOmi, _Steps.permissions]);
      expect(_Steps.progressSteps(pairedOmi: false), isNot(contains(_Steps.connect)));
    });

    test('a relaunch resumes the saved step, otherwise Connect', () {
      expect(_Steps.resume(_Steps.connect), _Steps.connect);
      expect(_Steps.resume(_Steps.language), _Steps.language);
      expect(_Steps.resume(_Steps.setup), _Steps.setup);
      for (final invalid in [-1, 0, 1, 10]) {
        expect(_Steps.resume(invalid), _Steps.connect, reason: 'saved $invalid');
      }
    });

    test('control order is unchanged for readers the flag does not assign', () {
      expect(OnboardingProgressStepsForTest.steps,
          [_Steps.name, _Steps.language, _Steps.foundOmi, _Steps.permissions, _Steps.voiceIntro]);
      expect(OnboardingWrapper.resumeStepForTesting(-1), _Steps.name);
      expect(OnboardingWrapper.resumeStepForTesting(_Steps.connect), _Steps.connect);
      expect(
          OnboardingWrapper.previousStepForTesting(
              currentIndex: _Steps.connect, setupPageEnabled: false, knowledgeGraphStepEnabled: false),
          _Steps.voiceIntro);
      expect(
          OnboardingWrapper.previousStepForTesting(
              currentIndex: _Steps.name, setupPageEnabled: false, knowledgeGraphStepEnabled: false),
          isNull);
    });
  });

  group('wrapper', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      SharedPreferencesUtil().uid = 'u1';
      AuthService.installLocalHarnessTokenGateway(_SignedIn());
      OnboardingVariantGate.resetForTesting();
      PaywallExperiment.resetForTesting();
    });

    testWidgets('connect_first: Connect right after consent, no Back; Skip moves on to Name', (tester) async {
      await _pumpAtConsent(tester, 'connect_first');
      await _agree(tester);

      expect(find.byKey(const Key('first_capture_omi')), findsOneWidget);
      expect(find.text(_controlSubtitle), findsOneWidget);
      expect(find.byKey(const Key('onboarding_back')), findsNothing);
      expect(find.byType(OnboardingProgressDots), findsNothing);

      await tester.tap(find.byKey(const Key('onboarding_complete_start')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      expect(find.byKey(const Key('onboarding_name_continue')), findsOneWidget);
      expect(find.byKey(const Key('onboarding_back')), findsNothing, reason: 'Name never leads back to Connect');
      expect(_dots(tester).current, 0);
      expect(_dots(tester).total, 5, reason: 'no Omi paired: the voice intro is still ahead');
      expect(SharedPreferencesUtil().getInt('onboarding/connectFirst/resumeStep/u1', defaultValue: -1), _Steps.name);
      expect(SharedPreferencesUtil().getInt('onboarding/resumeStep/u1', defaultValue: -1), -1);
    });

    testWidgets('connect_first: Back from the Connect page returns to the choices; a retry pairs and moves on to Name',
        (tester) async {
      final lane = _Lane();
      await _pumpWrapper(tester, 'connect_first', lane);
      await _agree(tester);

      // Cancel: Back on the Connect page lands on the Connect step again, with its choices working.
      await _openConnectPage(tester);
      expect(_omiRow(), findsOneWidget);
      await tester.tap(find.byType(OmiBackButton));
      await _settle(tester);
      expect(find.byType(ConnectDevicePage), findsNothing);
      expect(find.byKey(const Key('first_capture_omi')), findsOneWidget);
      expect(find.byKey(const Key('onboarding_name_continue')), findsNothing);
      expect(find.byKey(const Key('onboarding_back')), findsNothing);

      // Retry: the same button opens the page again; choosing the Omi pairs it and the wrapper moves on.
      await _openConnectPage(tester);
      await tester.tap(_omiRow());
      await _settle(tester);
      expect(find.byType(ConnectDevicePage), findsNothing);
      expect(find.byKey(const Key('onboarding_name_continue')), findsOneWidget);
      expect(find.byKey(const Key('onboarding_back')), findsNothing);
      expect(_dots(tester).total, 4, reason: 'paired: the voice intro is no longer ahead');
      expect(SharedPreferencesUtil().onboardingCompleted, isFalse, reason: 'pairing first does not finish onboarding');
      expect(lane.pairing.scans, 2);
    });

    testWidgets('connect_first: denied Bluetooth shows the recovery prompt to Settings; Scan Again then pairs',
        (tester) async {
      var settingsOpened = 0;
      _mockPermissions(onOpenSettings: () => settingsOpened++);
      final lane = _Lane()..bluetoothPermission = false;
      lane.pairing.bluetoothAllowed = false;
      await _pumpWrapper(tester, 'connect_first', lane);
      await _agree(tester);

      await _openConnectPage(tester);
      await _settle(tester);
      expect(find.text('Permissions Required'), findsOneWidget);
      await tester.tap(find.text('Open Settings'));
      await _settle(tester);
      expect(settingsOpened, 1);
      expect(find.text('Permissions Required'), findsNothing);
      expect(find.byKey(const Key('onboarding_name_continue')), findsNothing, reason: 'a denial never skips Connect');

      // Back from Settings with Bluetooth allowed: the page's own Scan Again finds the Omi.
      lane.bluetoothPermission = true;
      lane.pairing.bluetoothAllowed = true;
      await tester.tap(find.byKey(const Key('find_devices_scan_again')));
      await _settle(tester);
      await tester.tap(_omiRow());
      await _settle(tester);
      expect(find.byKey(const Key('onboarding_name_continue')), findsOneWidget);
      expect(_dots(tester).total, 4);
    });

    testWidgets(
        'connect_first: after pairing, relaunches resume on the arm\'s own step; Permissions opens Home with no '
        'voice intro', (tester) async {
      _mockPermissions();
      await _pumpWrapper(tester, 'connect_first', _Lane());
      await _agree(tester);
      await _openConnectPage(tester);
      await tester.tap(_omiRow());
      await _settle(tester);
      expect(find.byKey(const Key('onboarding_name_continue')), findsOneWidget);

      // Relaunch on Name: back on Name, not Connect, still four steps.
      await tester.pumpWidget(const SizedBox());
      await _pumpWrapper(tester, 'connect_first', _Lane());
      expect(find.byKey(const Key('onboarding_name_continue')), findsOneWidget);
      expect(find.byKey(const Key('first_capture_omi')), findsNothing);
      expect(_dots(tester).total, 4);

      // Relaunch on Permissions (Name, language and how you found us answered): Continue finishes
      // onboarding and opens Home; the voice intro never shows. Home's own cutover gate is held
      // closed so the test stops at Home's door instead of booting Home's services.
      AccountCutoverRuntime.instance.apply(AccountCutoverControl.unavailable(), authoritative: false);
      addTearDown(AccountCutoverRuntime.instance.resetForTesting);
      await tester.pumpWidget(const SizedBox());
      SharedPreferencesUtil().saveInt('onboarding/connectFirst/resumeStep/u1', _Steps.permissions);
      await _pumpWrapper(tester, 'connect_first', _Lane());
      expect(find.byKey(const Key('onboarding_permissions_continue')), findsOneWidget);
      expect(_dots(tester).current, 3);
      expect(_dots(tester).total, 4);
      await tester.tap(find.byKey(const Key('onboarding_permissions_continue')));
      for (var i = 0; i < 20 && find.byType(HomePageWrapper).evaluate().isEmpty; i++) {
        expect(find.byType(SpeechProfileWidget), findsNothing);
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(find.byType(HomePageWrapper), findsOneWidget);
      expect(find.byType(SpeechProfileWidget), findsNothing);
      expect(SharedPreferencesUtil().onboardingCompleted, isTrue);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('control (and an unread flag): Name first, no Connect step up front', (tester) async {
      for (final variant in ['control', null]) {
        await _pumpAtConsent(tester, variant);
        await _agree(tester);

        expect(find.byKey(const Key('onboarding_name_continue')), findsOneWidget, reason: 'variant $variant');
        expect(find.byKey(const Key('first_capture_omi')), findsNothing);
        expect(find.byKey(const Key('onboarding_back')), findsNothing);
        expect(_dots(tester).total, 5);
        expect(SharedPreferencesUtil().getInt('onboarding/connectFirst/resumeStep/u1', defaultValue: -1), -1);

        await tester.pumpWidget(const SizedBox());
        SharedPreferencesUtil().aiConsentGiven = false;
        OnboardingVariantGate.resetForTesting();
      }
    });
  });
}
