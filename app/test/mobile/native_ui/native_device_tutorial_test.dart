import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/interactive_device_onboarding_wrapper.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/steps/all_set_step.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/steps/voice_reply_step.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_intro_screen.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/services/voice_playback/voice_output_route.dart';
import 'package:omi/ui/ui.dart';

import 'native_test_host.dart';

/// Records the tutorial's batch-mode handshake without any capture, BLE or microphone behind it.
class _FakeCapture extends ChangeNotifier implements CaptureProvider {
  @override
  DeviceOnboardingProvider? deviceOnboardingProvider;
  int suspended = 0, restored = 0;

  @override
  Future<void> suspendBatchModeForOnboarding() async => suspended++;

  @override
  Future<void> restoreBatchModeAfterOnboarding() async => restored++;

  @override
  void cancelTutorialOwnedVoiceSession() {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeMessages extends ChangeNotifier implements MessageProvider {
  @override
  List<ServerMessage> messages = [];

  void receive(ServerMessage message) {
    messages = [...messages, message];
    notifyListeners();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// Completion persistence reaches the existing API owner; nothing listens on this address.
class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _FakeRouteSource implements VoiceOutputRouteSource {
  final _controller = StreamController<VoiceOutputRoute>.broadcast();

  @override
  Stream<VoiceOutputRoute> watch() => _controller.stream;

  void emit(VoiceOutputRoute route) => _controller.add(route);
}

ServerMessage _message(String id, String text, MessageSender sender) =>
    ServerMessage(id, DateTime(2026), text, sender, MessageType.text, null, false, [], [], []);

TranscriptSegment _segment(String text) => TranscriptSegment(
    id: 's', text: text, speaker: 'SPEAKER_00', isUser: true, personId: null, start: 0, end: 1, translations: []);

Map _snapshot(WidgetTester tester) => tester.widget<UiKitView>(find.byType(UiKitView)).creationParams as Map;

List<Map> _rows(WidgetTester tester) => [
      ...(_snapshot(tester)['toolbar'] as List).cast<Map>(),
      for (final section in (_snapshot(tester)['sections'] as List).cast<Map>())
        ...(section['rows'] as List).cast<Map>(),
    ];

Map? _row(WidgetTester tester, String id) => _rows(tester).where((row) => row['id'] == id).firstOrNull;

/// Sends [id] from the current native view exactly as Swift's command would, then lets Dart republish.
Future<void> _tap(WidgetTester tester, NativeTestHost host, String id, [Object? value]) async {
  final view = host.created.lastWhere((id) => !host.disposed.contains(id));
  final reply = await host.sendFromNative(view, MethodCall('action', {'id': id, 'value': value}));
  expect(const StandardMethodCodec().decodeEnvelope(reply!), isNull, reason: 'The row $id must dispatch');
  await NativeTestHost.settle(tester);
}

Widget _app(Widget child, {required CaptureProvider capture, MessageProvider? messages}) => MultiProvider(
      providers: [
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<MessageProvider>.value(value: messages ?? _FakeMessages()),
      ],
      child: NativeTestHost.app(child),
    );

/// A launcher route, so the tutorial is pushed and popped the way Device Settings opens it.
Widget _launcher() => Builder(
    builder: (context) => Scaffold(
        body: TextButton(
            onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(builder: (_) => const InteractiveDeviceOnboardingWrapper(allowExit: true))),
            child: const Text('open tutorial'))));

Future<void> _openTutorial(WidgetTester tester) async {
  await tester.tap(find.text('open tutorial'));
  await tester.pump();
  await tester.pump(const Duration(seconds: 1));
  await NativeTestHost.settle(tester);
}

/// The wrapper's chrome on every step: the close X and the progress row for step [n] of 6.
void _expectChrome(WidgetTester tester, int n) {
  expect(_row(tester, 'device_tutorial_close'), allOf(containsPair('symbol', 'xmark'), containsPair('title', 'Close')));
  expect(
      _row(tester, 'device_tutorial_step'),
      allOf(containsPair('kind', 'progress'), containsPair('value', n.toDouble()), containsPair('maximumValue', 6.0),
          containsPair('title', 'Step $n of 6')));
}

DeviceOnboardingProvider _provider(WidgetTester tester) =>
    Provider.of<DeviceOnboardingProvider>(tester.element(find.byType(IosNativeSurface)), listen: false);

void main() {
  setUpAll(() => Env.init(_UnreachableApiEnv()));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('the tutorial projects each step with native close and progress chrome', (tester) async {
    final host = NativeTestHost.install();
    final capture = _FakeCapture();
    final messages = _FakeMessages();
    await tester.pumpWidget(_app(_launcher(), capture: capture, messages: messages));
    await _openTutorial(tester);

    // Intro: the close X, art, copy, duration, Get Started and Skip; no progress before the steps.
    expect(capture.suspended, 1);
    expect(_snapshot(tester)['title'], 'Get to Know Your Omi');
    expect(_row(tester, 'device_tutorial_close'), containsPair('symbol', 'xmark'));
    expect(_row(tester, 'dev_tut_intro_duration'), containsPair('symbol', 'clock'));
    expect(_row(tester, 'dev_tut_skip'), containsPair('title', 'Skip'));
    expect(_row(tester, 'device_tutorial_step'), isNull);
    await _tap(tester, host, 'dev_tut_start');

    // Transcription demo.
    final provider = _provider(tester);
    _expectChrome(tester, 1);
    expect(_row(tester, 'dev_tut_transcription_status'), isNotNull);
    provider.onTranscriptSegments([_segment('one two three four **five**')]);
    await NativeTestHost.settle(tester);
    expect(_row(tester, 'dev_tut_transcription_done'), containsPair('symbol', 'checkmark.circle.fill'));
    expect(_row(tester, 'dev_tut_transcript'), containsPair('title', 'one two three four **five**'));
    expect(_row(tester, 'dev_tut_continue'), isNull, reason: 'Continue appears only after the classic delay');
    await tester.pump(const Duration(seconds: 1));
    await NativeTestHost.settle(tester);
    await _tap(tester, host, 'dev_tut_continue');

    // Single press: waiting, listening, processing, then the literal question and stripped answer.
    expect(provider.currentStep, DeviceOnboardingProvider.askQuestionStep);
    _expectChrome(tester, 2);
    expect(_row(tester, 'dev_tut_press_state'), containsPair('symbol', 'hand.tap'));
    provider.onButtonEvent(1);
    await NativeTestHost.settle(tester);
    expect(_row(tester, 'dev_tut_press_state'), containsPair('symbol', 'waveform'));
    provider.onButtonEvent(1);
    await NativeTestHost.settle(tester);
    expect(_row(tester, 'dev_tut_press_state'), containsPair('symbol', 'ellipsis.bubble'));
    messages.receive(_message('q', 'What is **Omi**?', MessageSender.human));
    messages.receive(_message('a', 'Omi is **your** AI _wearable_.', MessageSender.ai));
    await NativeTestHost.settle(tester);
    expect(_row(tester, 'dev_tut_press_state'), isNull);
    expect(
        _row(tester, 'dev_tut_question'),
        allOf(containsPair('kind', 'message_user'), containsPair('plainText', true),
            containsPair('title', 'What is **Omi**?')));
    expect(
        _row(tester, 'dev_tut_answer'),
        allOf(containsPair('kind', 'message_ai'), containsPair('plainText', true),
            containsPair('title', 'Omi is your AI wearable.')));
    expect(provider.aiResponse, 'Omi is **your** AI _wearable_.');
    await _tap(tester, host, 'dev_tut_continue');

    // Voice reply inside the wrapper (its playback has its own test with a fake output route).
    expect(provider.currentStep, DeviceOnboardingProvider.voiceReplyStep);
    _expectChrome(tester, 3);
    expect(_row(tester, 'dev_tut_preview'), isNotNull);
    // Re-entry from Settings preselects the stored preference, as the classic step does.
    final stored = SharedPreferencesUtil().voiceResponseMode;
    expect(provider.selectedVoiceResponseMode, stored);
    expect([for (var i = 0; i < 3; i++) _row(tester, 'dev_tut_mode_$i')!['value']],
        [for (var i = 0; i < 3; i++) i == stored]);
    await _tap(tester, host, 'dev_tut_continue');

    // Power cycle: hint, off, reconnect.
    expect(provider.currentStep, DeviceOnboardingProvider.powerCycleStep);
    _expectChrome(tester, 4);
    expect(_row(tester, 'dev_tut_power_state'), containsPair('symbol', 'power'));
    expect(_row(tester, 'dev_tut_power_hint'), isNull);
    await tester.pump(const Duration(seconds: 31));
    await NativeTestHost.settle(tester);
    expect(_row(tester, 'dev_tut_power_hint'), containsPair('title', contains('Hold the button firmly')));
    provider.onDeviceDisconnected();
    await tester.pump(const Duration(seconds: 1));
    await NativeTestHost.settle(tester);
    expect(_row(tester, 'dev_tut_power_state'), containsPair('symbol', 'bolt.horizontal.circle'));
    expect(_row(tester, 'dev_tut_power_hint'), isNull);
    provider.onDeviceReconnected();
    await NativeTestHost.settle(tester);
    expect(_row(tester, 'dev_tut_power_state'), containsPair('symbol', 'checkmark.circle'));
    expect(_row(tester, 'dev_tut_continue'), isNull);
    await tester.pump(const Duration(seconds: 1));
    await NativeTestHost.settle(tester);
    await _tap(tester, host, 'dev_tut_continue');

    // Double press: single-select actions, the single-tap hint, the prompt, then Continue.
    expect(provider.currentStep, DeviceOnboardingProvider.doublePressStep);
    _expectChrome(tester, 5);
    expect([for (var i = 0; i < 3; i++) _row(tester, 'dev_tut_double_$i')!['value']], [false, false, false]);
    expect(_row(tester, 'dev_tut_double_prompt'), isNull);
    await _tap(tester, host, 'dev_tut_double_1', true);
    expect(provider.selectedDoubleTapAction, 1);
    expect([for (var i = 0; i < 3; i++) _row(tester, 'dev_tut_double_$i')!['value']], [false, true, false]);
    expect(_row(tester, 'dev_tut_double_prompt'), containsPair('symbol', 'hand.tap'));
    provider.onButtonEvent(1);
    await NativeTestHost.settle(tester);
    expect(_row(tester, 'dev_tut_double_hint'), isNotNull);
    expect(_row(tester, 'dev_tut_continue'), isNull);
    provider.onButtonEvent(2);
    await NativeTestHost.settle(tester);
    expect(_row(tester, 'dev_tut_double_hint'), isNull);
    expect(SharedPreferencesUtil().doubleTapAction, 1);
    await _tap(tester, host, 'dev_tut_continue');

    // All set.
    expect(provider.currentStep, DeviceOnboardingProvider.allSetStep);
    _expectChrome(tester, 6);
    expect(_row(tester, 'dev_tut_all_set_double_tap'), containsPair('subtitle', contains('Mute')));
    expect(_row(tester, 'dev_tut_finish'), isNotNull);
    expect(tester.takeException(), isNull);
  });

  testWidgets('close persists device onboarding completion and leaves the tutorial', (tester) async {
    final host = NativeTestHost.install();
    final capture = _FakeCapture();
    await tester.pumpWidget(_app(_launcher(), capture: capture));
    await _openTutorial(tester);
    await _tap(tester, host, 'dev_tut_start');
    expect(SharedPreferencesUtil().deviceOnboardingCompleted, isFalse);

    await _tap(tester, host, 'device_tutorial_close');
    await tester.pump(const Duration(seconds: 1));
    expect(SharedPreferencesUtil().deviceOnboardingCompleted, isTrue);
    expect(find.byType(InteractiveDeviceOnboardingWrapper), findsNothing);
    expect(find.text('open tutorial'), findsOneWidget);
    expect(capture.restored, 1);
    expect(capture.deviceOnboardingProvider, isNull);
  });

  testWidgets('a refused step restores the classic frame, close X and progress dots', (tester) async {
    NativeTestHost.install(answer: (_, call) async {
      if (call.method == 'update') throw PlatformException(code: 'invalid_native_snapshot');
      return null;
    });
    await tester.pumpWidget(_app(_launcher(), capture: _FakeCapture()));
    await _openTutorial(tester);
    // The intro restores its own classic layout and its own close X.
    expect(find.byKey(const Key('device_onboarding_skip_button')), findsOneWidget);
    expect(find.byKey(const Key('device_onboarding_close_button')), findsOneWidget);
    await tester.tap(find.text('Get Started'));
    await tester.pump();
    await NativeTestHost.settle(tester);
    expect(find.text('Speak Into Your Omi'), findsOneWidget);
    expect(find.byKey(const Key('device_onboarding_close_button')), findsOneWidget);
    expect(find.byType(OnboardingProgressDots), findsOneWidget);
    expect(find.byType(UiKitView), findsNothing);

    await tester.tap(find.byKey(const Key('device_onboarding_close_button')));
    await tester.pump(const Duration(seconds: 1));
    expect(SharedPreferencesUtil().deviceOnboardingCompleted, isTrue);
  });

  testWidgets('voice reply previews through the route, persists the mode and Off stays silent', (tester) async {
    final host = NativeTestHost.install();
    // Preview haptics answer at once, so playback starts within the test's frames.
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (_) async => null);
    addTearDown(() => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null));
    final routes = _FakeRouteSource();
    final preview = Completer<void>();
    final played = <String>[];
    final modes = <int>[];
    var stops = 0;
    final provider = DeviceOnboardingProvider()..startOnboarding();
    await tester.pumpWidget(ChangeNotifierProvider.value(
        value: provider,
        child: NativeTestHost.app(Scaffold(
            body: VoiceReplyStep(
          firstRun: true,
          previewText: 'A useful answer',
          outputRouteSource: routes,
          playPreview: (text) {
            played.add(text);
            return preview.future;
          },
          stopPreview: () async => stops++,
          onModeAnalytics: modes.add,
          onComplete: () {},
        )))));
    await NativeTestHost.settle(tester);
    routes.emit(const VoiceOutputRoute.headphones('AirPods Pro'));
    await NativeTestHost.settle(tester);

    expect(provider.selectedVoiceResponseMode, 0);
    expect(SharedPreferencesUtil().voiceResponseMode, 0);
    expect(_row(tester, 'dev_tut_preview'),
        allOf(containsPair('symbol', 'play.fill'), containsPair('subtitle', 'Through AirPods Pro')));
    expect([for (var i = 0; i < 3; i++) _row(tester, 'dev_tut_mode_$i')!['value']], [true, false, false]);
    expect(
        _row(tester, 'dev_tut_voice_status'),
        allOf(containsPair('symbol', 'speaker.slash'),
            containsPair('title', 'Omi will stay silent. Answers still appear in the app.')));

    // Playing keeps the row actionable so the same row stops the preview.
    await _tap(tester, host, 'dev_tut_preview');
    expect(played, ['A useful answer']);
    expect(_row(tester, 'dev_tut_preview'), allOf(containsPair('symbol', 'stop.fill'), containsPair('enabled', true)));
    await _tap(tester, host, 'dev_tut_preview');
    expect(stops, 1);
    expect(_row(tester, 'dev_tut_preview'), containsPair('symbol', 'play.fill'));
    preview.complete();

    await _tap(tester, host, 'dev_tut_mode_1', true);
    expect(provider.selectedVoiceResponseMode, 1);
    expect(SharedPreferencesUtil().voiceResponseMode, 1);
    expect(modes, [1]);
    expect(
        _row(tester, 'dev_tut_voice_status'),
        allOf(containsPair('symbol', 'headphones'),
            containsPair('title', 'AirPods Pro connected. Omi will speak here.')));

    // Toggling the selected mode off keeps it selected, as tapping the selected card does today.
    await _tap(tester, host, 'dev_tut_mode_1', false);
    expect(provider.selectedVoiceResponseMode, 1);
    expect(_row(tester, 'dev_tut_mode_1'), containsPair('value', true));
    expect(modes, [1]);

    await _tap(tester, host, 'dev_tut_mode_0', true);
    expect(SharedPreferencesUtil().voiceResponseMode, 0);
    expect(modes, [1, 0]);
    expect(_row(tester, 'dev_tut_voice_status'), containsPair('symbol', 'speaker.slash'));
    expect(_row(tester, 'dev_tut_voice_hint'),
        containsPair('title', 'You can change this anytime in Settings › Voice Response'));

    await tester.pumpWidget(const SizedBox.shrink());
    expect(stops, 2, reason: 'Leaving the step stops the preview');
  });

  testWidgets('all-set rows summarize choices and reopen their steps; Finish completes', (tester) async {
    SharedPreferences.setMockInitialValues({'voiceResponseMode': 1, 'doubleTapAction': 2});
    await SharedPreferencesUtil.init();
    final host = NativeTestHost.install();
    var finished = 0;
    final provider = DeviceOnboardingProvider()
      ..startOnboarding()
      ..goToStep(DeviceOnboardingProvider.allSetStep);
    await tester.pumpWidget(ChangeNotifierProvider.value(
        value: provider, child: NativeTestHost.app(Scaffold(body: AllSetStep(onComplete: () => finished++)))));
    await NativeTestHost.settle(tester);

    expect(_row(tester, 'dev_tut_all_set_press_once'),
        allOf(containsPair('kind', 'navigation'), containsPair('subtitle', startsWith('1× · '))));
    expect(_row(tester, 'dev_tut_all_set_voice_reply'),
        allOf(containsPair('symbol', 'headphones'), containsPair('subtitle', 'Headphones only')));
    expect(
        _row(tester, 'dev_tut_all_set_double_tap'), containsPair('subtitle', endsWith('· Star Ongoing Conversation')));
    expect(_row(tester, 'dev_tut_all_set_replay'),
        containsPair('title', 'Replay this tour anytime in Settings › Device Settings › How to Use Your Omi'));

    for (final (id, step) in [
      ('dev_tut_all_set_press_once', DeviceOnboardingProvider.askQuestionStep),
      ('dev_tut_all_set_voice_reply', DeviceOnboardingProvider.voiceReplyStep),
      ('dev_tut_all_set_double_tap', DeviceOnboardingProvider.doublePressStep),
      ('dev_tut_all_set_hold', DeviceOnboardingProvider.powerCycleStep),
    ]) {
      provider.goToStep(DeviceOnboardingProvider.allSetStep);
      await NativeTestHost.settle(tester);
      await _tap(tester, host, id);
      expect(provider.currentStep, step);
    }
    await _tap(tester, host, 'dev_tut_finish');
    expect(finished, 1);
  });

  testWidgets('without the native host the tutorial keeps its classic presentation', (tester) async {
    expect(nativePresentationEnabled, isFalse);
    await tester.pumpWidget(_app(_launcher(), capture: _FakeCapture()));
    await _openTutorial(tester);
    expect(find.byType(IosNativeSurface), findsNothing);
    expect(find.byKey(const Key('device_onboarding_skip_button')), findsOneWidget);
  });

  testWidgets('with the flag on but SwiftUI unsupported the wrapper mounts the classic tree', (tester) async {
    NativeTestHost.install();
    final support = Completer<bool>();
    await tester.pumpWidget(_app(
        Builder(
            builder: (context) => Scaffold(
                body: TextButton(
                    onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                        builder: (_) =>
                            InteractiveDeviceOnboardingWrapper(allowExit: true, nativeSupport: () => support.future))),
                    child: const Text('open tutorial')))),
        capture: _FakeCapture()));
    await tester.tap(find.text('open tutorial'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.byType(OmiLoadingState), findsOneWidget, reason: 'Pending support shows the loading state');
    expect(find.byType(OnboardingIntroScreen), findsNothing);

    support.complete(false);
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.byType(IosNativeSurface), findsNothing);
    expect(find.byType(UiKitView), findsNothing);
    expect(find.byType(AnimatedSwitcher), findsOneWidget);
    expect(find.byKey(const Key('device_onboarding_skip_button')), findsOneWidget);

    await tester.tap(find.text('Get Started'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Speak Into Your Omi'), findsOneWidget);
    expect(find.byType(IosNativeSurface), findsNothing);
    expect(find.byType(OnboardingProgressDots), findsOneWidget);
    expect(find.byType(AnimatedSwitcher), findsNWidgets(2), reason: 'The classic intro and step transitions');
    expect(tester.takeException(), isNull);
  });
}
