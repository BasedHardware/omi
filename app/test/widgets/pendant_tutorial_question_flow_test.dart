import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/voice_question_result.dart';
import 'package:omi/models/plan_storefront.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/steps/single_press_step.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/services/voice_playback/omi_voice_playback_service.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';

import '../support/pendant_tutorial_harness.dart';

class _Env implements EnvFields {
  @override
  dynamic noSuchMethod(Invocation i) => null;
}

ServerMessage row(String id, String text, MessageSender sender) =>
    ServerMessage(id, DateTime.now(), text, sender, MessageType.text, null, false, [], [], []);
Stream<ServerMessageChunk> answered() async* {
  yield ServerMessageChunk('q', '', MessageChunkType.message, message: row('q', 'What is next?', MessageSender.human));
  yield ServerMessageChunk('a', '', MessageChunkType.done,
      message: row('a', 'Your meeting is at two.', MessageSender.ai));
}

Widget questionStep(PendantTutorialHarness h, {VoidCallback? onComplete}) =>
    ChangeNotifierProvider<DeviceOnboardingProvider>.value(
      value: h.tutorial,
      child: MaterialApp(
        theme: buildOmiTheme(),
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: SinglePressStep(onComplete: onComplete ?? () {})),
      ),
    );
MessageProvider messages(Stream<ServerMessageChunk> Function() stream,
        {Duration timeout = const Duration(seconds: 60)}) =>
    MessageProvider(
        voiceAudioFileSaver: (_, __, ___) async => File('/tmp/synthetic-tutorial.opus'),
        voiceReplyStreamer: (_, {language, abort}) => stream(),
        voiceReplyTimeout: timeout);

Future<void> flush(WidgetTester tester) async {
  // Event-loop turns for real Futures, without waiting for the animated graphic to settle.
  for (var i = 0; i < 10; i++) {
    await tester.pump(const Duration(milliseconds: 20));
    // SDK stream cancellation may return a completed Future created outside
    // FakeAsync. Drain that root-zone continuation before asserting the UI.
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() {
    try {
      Env.init(_Env());
    } catch (_) {}
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('dev.fluttercommunity.plus/package_info'),
        (call) async => {'appName': 'omi', 'packageName': 'com.omi.test', 'version': '0.0.0', 'buildNumber': '1'});
  });
  setUp(() async {
    OmiVoicePlaybackService.instance.debugHooks = const VoicePlaybackDebugHooks();
    SharedPreferences.setMockInitialValues({'deviceIdHash': 'fixture', 'voiceResponseMode': 0});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().voiceResponseMode = 0;
    await PlatformManager.initializeServices();
  });

  for (final target in ['main', 'past', 'persona', 'fresh']) {
    testWidgets('two button events complete the tutorial with $target chat open', (tester) async {
      final m = messages(answered);
      final app = AppProvider();
      addTearDown(app.dispose);
      if (target == 'past') m.chatSessionId = 'older-chat';
      if (target == 'persona') {
        app.setSelectedChatAppId('mentor');
        m.updateAppProvider(app);
      }
      if (target == 'fresh') m.isFreshChat = true;
      final h = PendantTutorialHarness(m);
      addTearDown(h.dispose);
      var continued = false;
      await tester.pumpWidget(questionStep(h, onComplete: () => continued = true));
      h.press();
      await tester.pump();
      expect(h.tutorial.voiceSessionActive, isTrue);
      h.feed();
      h.press();
      await flush(tester);
      expect(find.text('Your meeting is at two.'), findsOneWidget);
      expect(find.text('What is next?'), findsOneWidget);
      expect(find.textContaining('Processing your question'), findsNothing);
      await tester.tap(find.text('Continue'));
      expect(continued, isTrue);
      if (target != 'main') expect(m.messages, isEmpty, reason: 'Tutorial must preserve chat isolation');
      await tester.pumpWidget(const SizedBox());
      h.dispose();
      await tester.pump();
    });
  }

  for (final failure in ['no_speech', 'quota_exceeded', 'server', 'transport', 'incomplete', 'timeout', 'heartbeats']) {
    testWidgets('$failure leaves a retryable question; a fresh question succeeds', (tester) async {
      var count = 0;
      Stream<ServerMessageChunk> stream() {
        if (count++ > 0) return answered();
        if (failure == 'transport') return Stream.error(const SocketException('fixture offline'));
        if (failure == 'incomplete') return const Stream.empty();
        if (failure == 'timeout') return StreamController<ServerMessageChunk>().stream;
        if (failure == 'heartbeats') {
          return Stream.periodic(
              const Duration(milliseconds: 5), (_) => ServerMessageChunk('thinking', '', MessageChunkType.think));
        }
        return Stream.value(ServerMessageChunk('error', 'fixture failure', MessageChunkType.error, errorCode: failure));
      }

      final h = PendantTutorialHarness(messages(stream, timeout: const Duration(milliseconds: 30)));
      addTearDown(h.dispose);
      await tester.pumpWidget(questionStep(h));
      h.submit();
      await flush(tester);
      expect(h.tutorial.questionFailed, isTrue);
      expect(h.tutorial.questionSent, isFalse);
      expect(find.textContaining('Processing your question'), findsNothing);
      if (failure == 'no_speech') expect(find.text("Didn't catch that — try again"), findsOneWidget);
      if (failure == 'quota_exceeded') {
        expect(find.text('Chat limit reached. Upgrade for more messages.'), findsOneWidget);
      }
      h.submit();
      await flush(tester);
      expect(find.text('Your meeting is at two.'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      h.dispose();
      await tester.pump();
    });
  }

  testWidgets('codec failure returns to the press prompt and retries without losing data', (tester) async {
    var calls = 0;
    final h = PendantTutorialHarness(messages(answered), codec: (_) async {
      if (calls++ == 0) throw StateError('fixture codec unavailable');
      return BleAudioCodec.opus;
    });
    addTearDown(h.dispose);
    await tester.pumpWidget(questionStep(h));
    h.submit();
    await flush(tester);
    expect(h.tutorial.questionFailure, VoiceQuestionFailure.unavailable);
    expect(find.textContaining('Processing your question'), findsNothing);
    h.submit();
    await flush(tester);
    expect(find.text('Your meeting is at two.'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    h.dispose();
    await tester.pump();
  });

  testWidgets('unrelated chat traffic cannot complete a pending question; extra presses do not start another',
      (tester) async {
    final response = StreamController<ServerMessageChunk>();
    final h = PendantTutorialHarness(messages(() => response.stream));
    addTearDown(h.dispose);
    await tester.pumpWidget(questionStep(h));
    h.submit();
    await flush(tester);
    h.messages.addMessage(row('unrelated', 'Unrelated answer', MessageSender.ai));
    h.press();
    await flush(tester);
    expect(h.tutorial.voiceSessionActive, isFalse);
    expect(h.capture.hasVoiceCommandSessionForTesting, isFalse);
    expect(h.tutorial.aiResponse, isNull);
    response.add(ServerMessageChunk('a', '', MessageChunkType.done, message: row('a', 'Own answer', MessageSender.ai)));
    await flush(tester);
    expect(find.text('Own answer'), findsOneWidget);
    await tester.runAsync(() => response.close());
    await tester.pumpWidget(const SizedBox());
    h.dispose();
    await tester.pump();
  });

  testWidgets('late answer after exit and restart cannot complete a different tutorial attempt', (tester) async {
    final response = StreamController<ServerMessageChunk>();
    final h = PendantTutorialHarness(messages(() => response.stream));
    addTearDown(h.dispose);
    await tester.pumpWidget(questionStep(h));
    h.submit();
    await flush(tester);
    h.tutorial
      ..completeOnboarding()
      ..startOnboarding()
      ..advanceStep();
    response
        .add(ServerMessageChunk('old', '', MessageChunkType.done, message: row('old', 'Old answer', MessageSender.ai)));
    await flush(tester);
    expect(h.tutorial.aiResponse, isNull);
    expect(find.text('Old answer'), findsNothing);
    expect(h.tutorial.voiceSessionActive, isFalse);
    await tester.runAsync(() => response.close());
    await tester.pumpWidget(const SizedBox());
    h.dispose();
    await tester.pump();
  });
  for (final failure in ['busy', 'local quota', 'audio save']) {
    testWidgets('$failure reports a terminal result and permits a new question', (tester) async {
      var failSave = failure == 'audio save';
      final m = MessageProvider(
        voiceAudioFileSaver: (_, __, ___) async {
          if (failSave) throw const FileSystemException('fixture storage unavailable');
          return File('/tmp/synthetic-tutorial.opus');
        },
        voiceReplyStreamer: (_, {language, abort}) => answered(),
      );
      if (failure == 'busy') m.sendingMessage = true;
      if (failure == 'local quota') {
        m.applyChatAtCap(ChatAtCap(
            title: 'Limit',
            body: 'Fixture',
            resetLine: 'Later',
            resetAt: DateTime.now().millisecondsSinceEpoch ~/ 1000 + 300));
      }
      final h = PendantTutorialHarness(m);
      addTearDown(h.dispose);
      await tester.pumpWidget(questionStep(h));
      h.submit();
      await flush(tester);
      expect(h.tutorial.questionFailed, isTrue);
      expect(find.textContaining('Processing your question'), findsNothing);
      m.sendingMessage = false;
      m.applyChatAtCap(null);
      failSave = false;
      h.submit();
      await flush(tester);
      expect(find.text('Your meeting is at two.'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      h.dispose();
      await tester.pump();
    });
  }

  testWidgets('a pending Bluetooth haptic cannot block no-speech recovery or retry', (tester) async {
    final connection = Completer<DeviceConnection?>();
    var lookups = 0;
    var requests = 0;
    final h = PendantTutorialHarness(messages(() {
      if (requests++ > 0) return answered();
      return Stream.value(ServerMessageChunk('e', 'No speech', MessageChunkType.error, errorCode: 'no_speech'));
    }), connection: (_) {
      lookups++;
      return connection.future;
    });
    addTearDown(h.dispose);
    await tester.pumpWidget(questionStep(h));
    h.submit();
    await flush(tester);
    expect(lookups, greaterThan(0));
    expect(connection.isCompleted, isFalse);
    expect(h.tutorial.questionFailure, VoiceQuestionFailure.noSpeech);
    expect(h.tutorial.questionSent, isFalse);
    h.submit();
    await flush(tester);
    expect(find.text('Your meeting is at two.'), findsOneWidget);
    connection.complete(null);
    await flush(tester);
    await tester.pumpWidget(const SizedBox());
    h.dispose();
    await tester.pump();
  });

  testWidgets('held spoken-output setup times out and retries; a late setup cannot speak', (tester) async {
    SharedPreferencesUtil().voiceResponseMode = 2;
    final output = Completer<VoicePlaybackOutputSnapshot>();
    var probes = 0;
    var syntheses = 0;
    OmiVoicePlaybackService.instance.debugHooks = VoicePlaybackDebugHooks(
      probeOutput: () {
        if (probes++ == 0) return output.future;
        return Future.value(const VoicePlaybackOutputSnapshot(
            headphonesConnected: true, checkFailed: false, route: VoiceReplyPlaybackOutputRoute.bluetooth));
      },
      synthesize: ({required text, voiceId}) async {
        syntheses++;
        return null;
      },
      speak: (_) async {},
      delay: (_) async {},
    );
    final h = PendantTutorialHarness(messages(answered, timeout: const Duration(milliseconds: 30)));
    addTearDown(h.dispose);
    await tester.pumpWidget(questionStep(h));
    h.submit();
    await flush(tester);
    expect(probes, 1);
    expect(output.isCompleted, isFalse);
    expect(h.tutorial.questionFailed, isTrue);
    expect(h.tutorial.questionSent, isFalse);
    expect(find.textContaining('Processing your question'), findsNothing);
    h.submit();
    await flush(tester);
    expect(find.text('Your meeting is at two.'), findsOneWidget);
    expect(probes, 2);
    final synthesesBeforeLateSetup = syntheses;
    output.complete(const VoicePlaybackOutputSnapshot(
        headphonesConnected: true, checkFailed: false, route: VoiceReplyPlaybackOutputRoute.bluetooth));
    await flush(tester);
    expect(syntheses, synthesesBeforeLateSetup,
        reason: 'retired setup cannot start playback after the question has failed');
    await tester.tap(find.text('Continue'));
    await tester.pumpWidget(const SizedBox());
    h.dispose();
    OmiVoicePlaybackService.instance.debugReset();
    await tester.pump();
  });

  testWidgets('held spoken-output cleanup cannot block a failure or the next question', (tester) async {
    SharedPreferencesUtil().voiceResponseMode = 2;
    final cleanup = Completer<void>();
    var holdStop = false;
    var stops = 0;
    var requests = 0;
    OmiVoicePlaybackService.instance.debugHooks = VoicePlaybackDebugHooks(
      probeOutput: () async => const VoicePlaybackOutputSnapshot(
          headphonesConnected: true, checkFailed: false, route: VoiceReplyPlaybackOutputRoute.bluetooth),
      stopPlayback: () {
        stops++;
        return holdStop ? cleanup.future : Future.value();
      },
      synthesize: ({required text, voiceId}) async => null,
      speak: (_) async {},
      delay: (_) async {},
    );
    final h = PendantTutorialHarness(messages(() {
      if (requests++ > 0) return answered();
      holdStop = true;
      return Stream.value(ServerMessageChunk('error', 'No speech', MessageChunkType.error, errorCode: 'no_speech'));
    }));
    addTearDown(h.dispose);
    await tester.pumpWidget(questionStep(h));
    h.submit();
    await flush(tester);
    expect(stops, greaterThan(1));
    expect(cleanup.isCompleted, isFalse);
    expect(h.tutorial.questionFailure, VoiceQuestionFailure.noSpeech);
    expect(find.textContaining('Processing your question'), findsNothing);
    holdStop = false;
    h.submit();
    await flush(tester);
    expect(find.text('Your meeting is at two.'), findsOneWidget);
    cleanup.complete();
    await flush(tester);
    await tester.pumpWidget(const SizedBox());
    h.dispose();
    OmiVoicePlaybackService.instance.debugReset();
    await tester.pump();
  });

  testWidgets('auto-submit shows its answer and ignores a late second press', (tester) async {
    final response = StreamController<ServerMessageChunk>();
    final h = PendantTutorialHarness(messages(() => response.stream));
    addTearDown(h.dispose);
    await tester.pumpWidget(questionStep(h));
    h.press();
    h.feed();
    h.capture.endVoiceCommandSessionForTesting('fixture-pendant', autoSubmitted: true);
    await flush(tester);
    h.press();
    await tester.pump();
    expect(h.tutorial.questionSent, isTrue);
    expect(h.tutorial.voiceSessionActive, isFalse);
    expect(h.capture.hasVoiceCommandSessionForTesting, isFalse);
    response
        .add(ServerMessageChunk('a', '', MessageChunkType.done, message: row('a', 'Auto answer', MessageSender.ai)));
    await flush(tester);
    expect(find.text('Auto answer'), findsOneWidget);
    await tester.runAsync(() => response.close());
    await tester.pumpWidget(const SizedBox());
    h.dispose();
    await tester.pump();
  });
}
