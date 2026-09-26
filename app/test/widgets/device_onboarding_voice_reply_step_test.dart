import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/steps/all_set_step.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/steps/voice_reply_step.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/services/voice_playback/voice_output_route.dart';
import 'package:omi/ui/ui.dart';

class _FakeRouteSource implements VoiceOutputRouteSource {
  final _controller = StreamController<VoiceOutputRoute>.broadcast();

  @override
  Stream<VoiceOutputRoute> watch() => _controller.stream;

  void emit(VoiceOutputRoute route) => _controller.add(route);

  Future<void> close() => _controller.close();
}

Widget _app({required DeviceOnboardingProvider provider, required Widget child}) {
  return ChangeNotifierProvider.value(
    value: provider,
    child: MaterialApp(
      theme: buildOmiTheme(),
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(backgroundColor: OmiColors.surface0, body: SafeArea(child: child)),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('first run preselects and persists Off, then selection persists and records analytics', (tester) async {
    tester.view.physicalSize = const Size(393, 852);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final provider = DeviceOnboardingProvider()..startOnboarding();
    final routes = _FakeRouteSource();
    final analyticsModes = <int>[];
    addTearDown(routes.close);

    await tester.pumpWidget(_app(
      provider: provider,
      child: VoiceReplyStep(
        firstRun: true,
        previewText: null,
        outputRouteSource: routes,
        playPreview: (_) async {},
        stopPreview: () async {},
        onModeAnalytics: analyticsModes.add,
        onComplete: () {},
      ),
    ));

    expect(provider.selectedVoiceResponseMode, 0);
    expect(SharedPreferencesUtil().voiceResponseMode, 0);

    await tester.tap(find.byKey(const Key('voice_reply_mode_headphones')));
    await tester.pump();

    expect(provider.selectedVoiceResponseMode, 1);
    expect(SharedPreferencesUtil().voiceResponseMode, 1);
    expect(analyticsModes, [1]);
  });

  testWidgets('settings re-entry preselects the current preference', (tester) async {
    SharedPreferences.setMockInitialValues({'voiceResponseMode': 2});
    await SharedPreferencesUtil.init();
    tester.view.physicalSize = const Size(393, 852);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final provider = DeviceOnboardingProvider()..startOnboarding();
    final routes = _FakeRouteSource();
    addTearDown(routes.close);

    await tester.pumpWidget(_app(
      provider: provider,
      child: VoiceReplyStep(
        firstRun: false,
        outputRouteSource: routes,
        playPreview: (_) async {},
        stopPreview: () async {},
        onComplete: () {},
      ),
    ));

    expect(provider.selectedVoiceResponseMode, 2);
    expect(SharedPreferencesUtil().voiceResponseMode, 2);
  });

  testWidgets('output status updates live for connected headphones and phone speaker', (tester) async {
    SharedPreferences.setMockInitialValues({'voiceResponseMode': 1});
    await SharedPreferencesUtil.init();
    tester.view.physicalSize = const Size(393, 852);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final provider = DeviceOnboardingProvider()..startOnboarding();
    final routes = _FakeRouteSource();
    addTearDown(routes.close);

    await tester.pumpWidget(_app(
      provider: provider,
      child: VoiceReplyStep(
        firstRun: false,
        outputRouteSource: routes,
        playPreview: (_) async {},
        stopPreview: () async {},
        onComplete: () {},
      ),
    ));

    routes.emit(const VoiceOutputRoute.headphones('AirPods Pro'));
    await tester.pump();
    expect(find.text('AirPods Pro · Connected'), findsOneWidget);

    routes.emit(const VoiceOutputRoute.speaker());
    await tester.pump();
    expect(find.text('Headphones only · Disconnected'), findsOneWidget);

    routes.emit(const VoiceOutputRoute.unknown());
    await tester.pump();
    expect(find.text('Audio Output · Disconnected'), findsOneWidget);

    await tester.tap(find.byKey(const Key('voice_reply_mode_always')));
    routes.emit(const VoiceOutputRoute.speaker());
    await tester.pump();
    expect(find.text('Speaker · Connected'), findsOneWidget);
  });

  testWidgets('leaving the step stops an in-flight preview', (tester) async {
    tester.view.physicalSize = const Size(393, 852);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final provider = DeviceOnboardingProvider()..startOnboarding();
    final routes = _FakeRouteSource();
    final previewCompleter = Completer<void>();
    var stopCalls = 0;
    addTearDown(routes.close);

    await tester.pumpWidget(_app(
      provider: provider,
      child: VoiceReplyStep(
        firstRun: true,
        outputRouteSource: routes,
        playPreview: (_) => previewCompleter.future,
        stopPreview: () async => stopCalls++,
        onComplete: () {},
      ),
    ));

    await tester.tap(find.byKey(const Key('voice_reply_preview_button')));
    await tester.pump();
    expect(find.byIcon(Icons.stop_rounded), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
    expect(stopCalls, 1);
    previewCompleter.complete();
  });

  testWidgets('All Set summarizes choices and every row reopens its step', (tester) async {
    SharedPreferences.setMockInitialValues({'voiceResponseMode': 1, 'doubleTapAction': 2});
    await SharedPreferencesUtil.init();
    tester.view.physicalSize = const Size(393, 852);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final provider = DeviceOnboardingProvider()
      ..startOnboarding()
      ..goToStep(DeviceOnboardingProvider.allSetStep);

    await tester.pumpWidget(_app(provider: provider, child: AllSetStep(onComplete: () {})));

    expect(find.text("You're All Set"), findsOneWidget);
    expect(find.text('Headphones only'), findsOneWidget);
    expect(find.text('Star Ongoing Conversation'), findsOneWidget);
    expect(find.byKey(const Key('all_set_press_once')), findsOneWidget);
    expect(find.byKey(const Key('all_set_voice_reply')), findsOneWidget);
    expect(find.byKey(const Key('all_set_double_tap')), findsOneWidget);
    expect(find.byKey(const Key('all_set_hold')), findsOneWidget);

    for (final (key, step) in [
      ('all_set_press_once', DeviceOnboardingProvider.askQuestionStep),
      ('all_set_voice_reply', DeviceOnboardingProvider.voiceReplyStep),
      ('all_set_double_tap', DeviceOnboardingProvider.doublePressStep),
      ('all_set_hold', DeviceOnboardingProvider.powerCycleStep),
    ]) {
      provider.goToStep(DeviceOnboardingProvider.allSetStep);
      await tester.pump();
      await tester.tap(find.byKey(Key(key)));
      expect(provider.currentStep, step);
    }
  });

  test('tutorial has six ordered steps and preserves the answer for voice preview', () {
    final provider = DeviceOnboardingProvider()..startOnboarding();
    provider.goToStep(DeviceOnboardingProvider.askQuestionStep);
    provider.onVoiceResponseReceived('A useful answer');
    provider.advanceStep();

    expect(DeviceOnboardingProvider.totalSteps, 6);
    expect(provider.currentStep, DeviceOnboardingProvider.voiceReplyStep);
    expect(provider.aiResponse, 'A useful answer');
  });
}
