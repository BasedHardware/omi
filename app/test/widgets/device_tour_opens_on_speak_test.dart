import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/interactive_device_onboarding_wrapper.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

import '../support/recording_analytics.dart';

/// The tour's whole capture boundary: it attaches itself, pauses Transcribe Later while open, and on exit
/// cancels only a voice session it started. Any other capture call fails the test.
class _Capture extends ChangeNotifier implements CaptureProvider {
  @override
  DeviceOnboardingProvider? deviceOnboardingProvider;
  final calls = <String>[];

  @override
  Future<void> suspendBatchModeForOnboarding() async => calls.add('suspend');
  @override
  Future<void> restoreBatchModeAfterOnboarding() async => calls.add('restore');
  @override
  void cancelTutorialOwnedVoiceSession() => calls.add('cancelTutorialVoice');
  @override
  dynamic noSuchMethod(Invocation i) => throw StateError('Unexpected capture call: ${i.memberName}');
}

class _Session implements AuthTokenGateway {
  @override
  AuthUserSnapshot get currentUser => const AuthUserSnapshot(uid: 'tour-owner');
  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;
  @override
  Future<void> signOut() async {}
}

class _Env implements EnvFields {
  @override
  dynamic noSuchMethod(Invocation i) => null;
}

const _speakTitle = 'Speak Into Your Omi';
const _speakSubtitle = 'Say something like\n“Remind me to call Sam tomorrow.”';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late _Capture capture;
  late RecordingAnalytics analytics;
  final navigator = GlobalKey<NavigatorState>();

  setUpAll(() {
    try {
      Env.init(_Env());
    } catch (_) {}
    PackageInfo.setMockInitialValues(
        appName: 'Omi Test', packageName: 'com.omi.test', version: '1.0.0', buildNumber: '1', buildSignature: '');
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    AuthService.installLocalHarnessTokenGateway(_Session());
    analytics = RecordingAnalytics();
    AnalyticsManager.resetForTesting();
    AnalyticsManager.configure(analytics.adapter);
    await AnalyticsManager.init();
    capture = _Capture();
  });

  tearDown(AnalyticsManager.resetForTesting);

  Future<void> frames(WidgetTester tester, [int count = 6]) async {
    // The step's pulse animation repeats forever, so pumpAndSettle never settles.
    for (var i = 0; i < count; i++) {
      await tester.pump(const Duration(milliseconds: 200));
    }
  }

  Future<void> openTour(WidgetTester tester) async {
    await tester.pumpWidget(ChangeNotifierProvider<CaptureProvider>.value(
      value: capture,
      child: MaterialApp(
        navigatorKey: navigator,
        theme: buildOmiTheme(),
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: const Scaffold(body: Text('Home')),
      ),
    ));
    // The same push Home makes once a CV1 connects.
    navigator.currentState!.push(MaterialPageRoute(builder: (_) => const InteractiveDeviceOnboardingWrapper()));
    await frames(tester);
  }

  Future<void> speak(WidgetTester tester, String words) async {
    capture.deviceOnboardingProvider!.onTranscriptSegments([
      TranscriptSegment(
          id: 's0',
          text: words,
          speaker: 'SPEAKER_00',
          isUser: true,
          personId: null,
          start: 0,
          end: 2,
          translations: []),
    ]);
    await frames(tester, 8);
  }

  Future<List<String>> tourEvents(WidgetTester tester) async {
    await tester.runAsync(() => AnalyticsManager.flushPending(force: true));
    return analytics.names.where((name) => name.startsWith('Device Onboarding')).toList();
  }

  int dot(WidgetTester tester) =>
      tester.widget<OnboardingProgressDots>(find.byType(OnboardingProgressDots)).currentStep;

  testWidgets('opens on Speak Into Your Omi with the close X and no intro screen', (tester) async {
    await openTour(tester);

    expect(find.text(_speakTitle), findsOneWidget);
    expect(find.text(_speakSubtitle), findsOneWidget);
    expect(find.text('Get to Know Your Omi'), findsNothing);
    expect(find.text('Get Started'), findsNothing);
    expect(find.text('Skip'), findsNothing);
    expect(find.byKey(const Key('device_onboarding_close_button')), findsOneWidget);
    expect(find.bySemanticsLabel('Close'), findsOneWidget);
    expect(dot(tester), 0);

    // Live from the first frame: the pendant's words reach this step without a tap first.
    final tour = capture.deviceOnboardingProvider!;
    expect(tour.isOnboardingActive, isTrue);
    expect(tour.currentStep, DeviceOnboardingProvider.transcriptionStep);
    expect(capture.calls, ['suspend']);
    expect(await tourEvents(tester), ['Device Onboarding Started']);
    analytics.expectSingle('Device Onboarding Started', {'source': 'auto'});
  });

  testWidgets('spoken words fill the transcript card, then Continue opens the question step', (tester) async {
    await openTour(tester);
    await speak(tester, 'Remind me to call Sam tomorrow.');

    expect(find.text('Remind me to call Sam tomorrow.'), findsOneWidget);
    expect(find.text('Good job!'), findsOneWidget);
    await tester.tap(find.text('Continue'));
    await frames(tester);

    expect(capture.deviceOnboardingProvider!.currentStep, DeviceOnboardingProvider.askQuestionStep);
    expect(find.text('Press the button on your Omi'), findsOneWidget);
    expect(dot(tester), 1);
    expect(await tourEvents(tester), ['Device Onboarding Started', 'Device Onboarding Step Completed']);
    analytics.expectSingle('Device Onboarding Step Completed', {'step': 'transcription_demo'});
  });

  testWidgets('close X on the first screen leaves, saves the tour as done and reports step 0', (tester) async {
    await openTour(tester);

    await tester.tap(find.byKey(const Key('device_onboarding_close_button')));
    await frames(tester);

    expect(find.byType(InteractiveDeviceOnboardingWrapper), findsNothing);
    expect(find.text('Home'), findsOneWidget);
    expect(SharedPreferencesUtil().deviceOnboardingCompleted, isTrue);
    expect(capture.deviceOnboardingProvider, isNull);
    expect(capture.calls, ['suspend', 'cancelTutorialVoice', 'restore']);
    expect(await tourEvents(tester), ['Device Onboarding Started', 'Device Onboarding Abandoned']);
    analytics.expectSingle('Device Onboarding Abandoned', {'step': 0});
  });

  testWidgets('step indexes follow the screens: leaving on the second screen reports step 1', (tester) async {
    await openTour(tester);
    await speak(tester, 'Remind me to call Sam tomorrow.');
    await tester.tap(find.text('Continue'));
    await frames(tester);

    await tester.tap(find.byKey(const Key('device_onboarding_close_button')));
    await frames(tester);

    expect(find.byType(InteractiveDeviceOnboardingWrapper), findsNothing);
    expect(await tourEvents(tester),
        ['Device Onboarding Started', 'Device Onboarding Step Completed', 'Device Onboarding Abandoned']);
    analytics.expectSingle('Device Onboarding Abandoned', {'step': DeviceOnboardingProvider.askQuestionStep});
  });
}
