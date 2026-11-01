// Offline UI acceptance target. Buttons inject synthetic pendant events; this
// never connects a real pendant, records microphone audio or signs into Omi.
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/steps/single_press_step.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import '../test/support/pendant_tutorial_harness.dart';

class _Env implements EnvFields {
  @override
  dynamic noSuchMethod(Invocation i) => null;
}

Future<void> main() async {
  MarionetteBinding.ensureInitialized();
  Env.init(_Env());
  SharedPreferences.setMockInitialValues({'deviceIdHash': 'tutorial-fixture'});
  await SharedPreferencesUtil.init();
  SharedPreferencesUtil().voiceResponseMode = 0;
  await PlatformManager.initializeServices();
  OmiColors.active = OmiPalette.dark;
  runApp(const _Fixture());
}

class _Fixture extends StatefulWidget {
  const _Fixture();
  @override
  State<_Fixture> createState() => _FixtureState();
}

class _FixtureState extends State<_Fixture> {
  String _next = 'answer';
  bool _continued = false;
  late final _h = PendantTutorialHarness(MessageProvider(
    voiceReplyTimeout: const Duration(seconds: 3),
    voiceAudioFileSaver: (_, __, ___) async => File('/tmp/synthetic-tutorial.opus'),
    voiceReplyStreamer: (_, {language, abort}) async* {
      await Future<void>.delayed(const Duration(milliseconds: 300));
      if (_next == 'offline') throw const SocketException('synthetic offline');
      if (_next == 'no_speech') {
        yield ServerMessageChunk('error', 'No speech', MessageChunkType.error, errorCode: 'no_speech');
        return;
      }
      yield ServerMessageChunk('q', '', MessageChunkType.message,
          message: _row('q', 'What is next?', MessageSender.human));
      yield ServerMessageChunk('a', '', MessageChunkType.done,
          message: _row('a', 'Your meeting is at two.', MessageSender.ai));
    },
  )..chatSessionId = 'synthetic-past-chat');
  ServerMessage _row(String id, String text, MessageSender sender) =>
      ServerMessage(id, DateTime.now(), text, sender, MessageType.text, null, false, [], [], []);
  @override
  void dispose() {
    _h.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MultiProvider(
        providers: [
          ChangeNotifierProvider<DeviceOnboardingProvider>.value(value: _h.tutorial),
          ChangeNotifierProvider<MessageProvider>.value(value: _h.messages),
        ],
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: buildOmiTheme(),
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            appBar: AppBar(title: const Text('Synthetic pendant QA'), actions: [
              IconButton(
                  key: const Key('fixture_restart'),
                  tooltip: 'Restart fixture',
                  icon: const Icon(Icons.refresh),
                  onPressed: () {
                    _h.capture.cancelActiveVoiceSession();
                    _h.tutorial
                      ..startOnboarding()
                      ..advanceStep();
                    setState(() => _continued = false);
                  }),
            ]),
            body: _continued
                ? const Center(child: Text('Tutorial continued', key: Key('fixture_continued')))
                : SinglePressStep(onComplete: () => setState(() => _continued = true)),
            bottomNavigationBar: SafeArea(
                child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Text('Synthetic audio · past chat selected · no network'),
              Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
                DropdownButton<String>(
                    key: const Key('fixture_response'),
                    value: _next,
                    items: const ['answer', 'offline', 'no_speech']
                        .map((v) => DropdownMenuItem(value: v, child: Text(v)))
                        .toList(),
                    onChanged: (v) => setState(() => _next = v!)),
                TextButton(
                    key: const Key('fixture_pendant_press'),
                    onPressed: () {
                      _h.press();
                      if (_h.capture.hasVoiceCommandSessionForTesting) _h.feed();
                    },
                    child: const Text('Press pendant')),
              ]),
            ])),
          ),
        ),
      );
}
