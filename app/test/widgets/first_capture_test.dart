import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/complete_screen.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/pages/onboarding/onboarding_step_telemetry.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/widgets/connection_guide_sheet.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/backend/preferences.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../integration_test/visual_audit/fakes.dart' show AuditDeviceProvider;
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

Widget host(Widget child, {TargetPlatform platform = TargetPlatform.iOS}) => MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: buildOmiTheme(brightness: Brightness.light).copyWith(
          platform: platform,
          snackBarTheme: buildOmiTheme(brightness: Brightness.light).snackBarTheme.copyWith(
              contentTextStyle: buildOmiTheme(brightness: Brightness.light)
                  .snackBarTheme
                  .contentTextStyle!
                  .copyWith(fontFamily: platform == TargetPlatform.iOS ? 'SF Pro Display' : 'Roboto')),
          appBarTheme: buildOmiTheme(brightness: Brightness.light).appBarTheme.copyWith(
              titleTextStyle:
                  OmiType.headline.copyWith(fontFamily: platform == TargetPlatform.iOS ? 'SF Pro Display' : 'Roboto')),
          textTheme: buildOmiTheme(brightness: Brightness.light)
              .textTheme
              .apply(fontFamily: platform == TargetPlatform.iOS ? 'SF Pro Display' : 'Roboto')),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: child),
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  testWidgets('pair cancel returns to choices; successful pair completes; skip emits properties', (tester) async {
    var paired = false, completed = 0;
    final events = <RegisteredEvent>[];
    final props = <String, Object>{};
    await tester.pumpWidget(host(OnboardingCompleteScreen(
        onComplete: () => completed++,
        emit: events.add,
        setProperty: (k, v) => props[k] = v,
        pairDevice: (_) async => paired)));
    await tester.tap(find.byKey(const Key('first_capture_omi')));
    await tester.pump();
    expect(completed, 0);
    expect(props, {'capture_choice': 'omi', 'has_omi_device': false});
    paired = true;
    await tester.tap(find.byKey(const Key('first_capture_omi')));
    await tester.pump();
    expect(completed, 1);
    expect(props['has_omi_device'], isTrue);
    await tester.tap(find.byKey(const Key('onboarding_complete_start')));
    expect(props['capture_choice'], 'skipped');
    expect(events.whereType<OnboardingFirstCaptureSkipped>().length, 1);
  });

  testWidgets('already saved Omi retains has_omi_device without a new pair', (tester) async {
    await SharedPreferencesUtil().btDeviceSet(BtDevice(id: 'saved-omi', name: 'Omi', type: DeviceType.omi, rssi: -40));
    final props = <String, Object>{};
    await tester.pumpWidget(host(
        OnboardingCompleteScreen(onComplete: () {}, emit: (_) {}, setProperty: (key, value) => props[key] = value)));
    await tester.tap(find.byKey(const Key('onboarding_complete_start')));
    expect(props['has_omi_device'], isTrue);
  });

  testWidgets('pair failure stays on Connect with How to pair; explicit Back returns to choices', (tester) async {
    final pairing = _RenderPairingProvider();
    var completed = 0;
    await tester.pumpWidget(MultiProvider(providers: [
      ChangeNotifierProvider<OnboardingProvider>.value(value: pairing),
      ChangeNotifierProvider<DeviceProvider>(create: (_) => AuditDeviceProvider()),
      ChangeNotifierProvider<HomeProvider>(create: (_) => _RenderHomeProvider()),
    ], child: host(OnboardingCompleteScreen(onComplete: () => completed++, emit: (_) {}, setProperty: (_, value) {}))));
    await tester.tap(find.byKey(const Key('first_capture_omi')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    pairing.pairingFailureReason = DeviceConnectFailureShownFailureReason.unknown;
    pairing.notifyError('DEVICE_CONNECT_FAILED');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(ConnectDevicePage), findsOneWidget);
    expect(find.text('An error occurred. Please try again.'), findsOneWidget);
    expect(find.text('How to pair'), findsOneWidget);
    expect(completed, 0);
    await tester.tap(find.text('How to pair'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(ConnectionGuideSheet), findsOneWidget);
    Navigator.of(tester.element(find.byType(ConnectionGuideSheet))).pop();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(ConnectionGuideSheet), findsNothing);
    await tester.tap(find.byType(OmiBackButton));
    await tester.pumpAndSettle();
    expect(find.byType(ConnectDevicePage), findsNothing);
    expect(find.byKey(const Key('first_capture_omi')), findsOneWidget);
    expect(completed, 0);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('no device opens the store in-app and returns to the choices, where Skip is one tap', (tester) async {
    var shopOpened = 0, completed = 0;
    final props = <String, Object>{};
    await tester.pumpWidget(host(OnboardingCompleteScreen(
        onComplete: () => completed++,
        emit: (_) {},
        setProperty: (k, v) => props[k] = v,
        openShop: (_) async => shopOpened++)));
    await tester.tap(find.byKey(const Key('first_capture_shop')));
    await tester.pumpAndSettle();
    expect(shopOpened, 1);
    expect(completed, 0);
    expect(find.byKey(const Key('first_capture_omi')), findsOneWidget);
    await tester.tap(find.byKey(const Key('onboarding_complete_start')));
    expect(completed, 1);
    expect(props['capture_choice'], 'skipped');
  });

  test('restored tracker emits no auth exit and records the actual Back reason', () {
    final events = <RegisteredEvent>[];
    final tracker =
        MobileOnboardingStepTelemetry(emit: events.add, platform: () => OnboardingStepCompletedPlatform.ios);
    tracker.seed(9);
    tracker.enter(9);
    expect(events, isEmpty);
    tracker.exitReason = OnboardingStepCompletedExitReason.back;
    tracker.enter(6);
    expect(events.single.properties['step'], 'first_capture');
    expect(events.single.properties['exit_reason'], 'back');
  });

  test('persisted completion resumes without moving indices or breaking prior saves', () async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    const key = 'onboarding/resumeStep/first-capture-test';
    await SharedPreferencesUtil().saveInt(key, 9);
    expect(OnboardingWrapper.resumeStepForTesting(SharedPreferencesUtil().getInt(key)), 9);
    expect(OnboardingWrapper.resumeStepForTesting(8), 8);
    expect(OnboardingWrapper.resumeStepForTesting(6), 6);
    expect(OnboardingWrapper.resumeStepForTesting(7), 9);
    expect(OnboardingWrapper.resumeStepForTesting(10), 2);
    expect(OnboardingWrapper.resumeStepForTesting(-1), 2);
  });

  test('step exits emit once, time every visit, and preserve explicit skips and Back', () {
    var ms = 0;
    final events = <RegisteredEvent>[];
    final tracker = MobileOnboardingStepTelemetry(
        emit: events.add, platform: () => OnboardingStepCompletedPlatform.ios, elapsedMs: () => ms);
    ms = 25;
    tracker.enter(1);
    tracker.enter(1);
    expect(events.length, 1);
    tracker.enter(9);
    ms = 100;
    tracker.skipped = true;
    tracker.exit();
    tracker.exit();
    expect(events.last.properties, {
      'step': 'first_capture',
      'index': 9,
      'elapsed_ms': 75,
      'skipped': true,
      'platform': 'ios',
      'exit_reason': 'skipped'
    });
    tracker.enter(6);
    tracker.enter(9);
    ms = 120;
    tracker.exit();
    expect(events.last.properties['skipped'], isFalse);
    expect(events.last.properties['elapsed_ms'], 20);
  });

  test('completion index remains resumable with both back destinations', () {
    expect(OnboardingProgressStepsForTest.completePage, 9);
    expect(OnboardingWrapper.isResumableStepForTesting(9), isTrue);
    expect(
        OnboardingWrapper.previousStepForTesting(
            currentIndex: 9, setupPageEnabled: false, knowledgeGraphStepEnabled: false),
        6);
    expect(
        OnboardingWrapper.previousStepForTesting(
            currentIndex: 9, setupPageEnabled: true, knowledgeGraphStepEnabled: false),
        8);
    for (final step in OnboardingStepCompletedStep.values) {
      final event = OnboardingStepCompleted(
          step: step,
          index: step.index,
          elapsedMs: 23,
          skipped: true,
          platform: OnboardingStepCompletedPlatform.android,
          exitReason: OnboardingStepCompletedExitReason.skipped);
      expect(event.properties.keys.toSet(), {'step', 'index', 'elapsed_ms', 'skipped', 'platform', 'exit_reason'});
      expect(event.properties['skipped'], isTrue);
    }
  });
}

class _RenderPairingProvider extends OnboardingProvider {
  @override
  Future<void> scanDevices({required VoidCallback onShowDialog, VoidCallback? onShowLocationDialog}) async {}
  @override
  void cancelActiveScan() {}
}

class _RenderHomeProvider extends HomeProvider {
  @override
  Future<void> setupHasSpeakerProfile() async {}
}
