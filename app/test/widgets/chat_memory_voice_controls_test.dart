import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/chat/widgets/jump_to_latest_button.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _SilentMessages extends MessageProvider {
  @override
  Future<void> fetchChatApps() async {}

  @override
  Future refreshMessages({bool dropdownSelected = false}) async {}
}

class _VoiceState extends VoiceRecorderProvider {
  _VoiceState(this.current);

  VoiceRecorderState current;
  int transcriptions = 0;
  int sends = 0;
  int discards = 0;

  @override
  VoiceRecorderState get state => current;
  @override
  bool get isActive => current != VoiceRecorderState.idle;
  @override
  bool get isRecording => current == VoiceRecorderState.recording;
  @override
  bool get hasPendingRecording => current == VoiceRecorderState.pendingRecovery;
  @override
  Future<void> startRecording() async {}
  @override
  Future<void> processRecording() async {
    transcriptions++;
  }

  @override
  void requestAutoSendOnNextTranscript() => sends++;
  @override
  Future<void> discardRecording() async {
    discards++;
    current = VoiceRecorderState.idle;
    notifyListeners();
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    VisibilityDetectorController.instance.updateInterval = Duration.zero;
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  Future<void> pumpChat(WidgetTester tester, _VoiceState voice, {List<ServerMessage> messages = const []}) async {
    final provider = _SilentMessages()..messages = messages;
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: MultiProvider(
        providers: [
          ChangeNotifierProvider<MessageProvider>.value(value: provider),
          ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
          ChangeNotifierProvider(create: (_) => HomeProvider()),
          ChangeNotifierProvider<VoiceRecorderProvider>.value(value: voice),
          ChangeNotifierProvider(create: (_) => AppProvider()),
          ChangeNotifierProvider(
              create: (_) => IntegrationProvider(
                    fetchStatus: (_) async => null,
                    saveStatus: (_, __) async => false,
                    deleteStatus: (_) async => false,
                    persistPref: (_, __) async {},
                  )),
        ],
        child: const ChatPage(),
      ),
    ));
    await tester.pump();
  }

  testWidgets('voice composer offers separate discard, transcribe and send actions', (tester) async {
    final voice = _VoiceState(VoiceRecorderState.recording);
    await pumpChat(tester, voice);

    expect(find.byKey(const ValueKey('omi.chat.voice.discard')), findsOneWidget);
    expect(find.byKey(const ValueKey('omi.chat.voice.transcribe')), findsOneWidget);
    expect(find.byKey(const ValueKey('omi.chat.voice.send')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('omi.chat.voice.transcribe')));
    expect(voice.transcriptions, 1);
    expect(voice.sends, 0);

    await tester.tap(find.byKey(const ValueKey('omi.chat.voice.send')));
    expect(voice.transcriptions, 2);
    expect(voice.sends, 1);

    await tester.tap(find.byKey(const ValueKey('omi.chat.voice.discard')));
    await tester.pump();
    expect(voice.discards, 1);
    expect(voice.transcriptions, 2);
  });

  for (final state in [VoiceRecorderState.transcribeFailed, VoiceRecorderState.pendingRecovery]) {
    testWidgets('discard is available in $state', (tester) async {
      final voice = _VoiceState(state);
      await pumpChat(tester, voice);
      expect(find.byKey(const ValueKey('omi.chat.voice.discard')), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('omi.chat.voice.discard')));
      await tester.pump();
      expect(voice.discards, 1);
      expect(voice.transcriptions, 0);
    });
  }

  testWidgets('Latest appears on scroll, hides after idle and reappears on activity', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final now = DateTime.utc(2026, 9, 27);
    final messages = List.generate(
        35,
        (i) => ServerMessage(
              'message-$i',
              now.add(Duration(minutes: i)),
              'Message $i with a longer transcript line',
              MessageSender.human,
              MessageType.text,
              null,
              false,
              [],
              [],
              [],
            ));
    await pumpChat(tester, _VoiceState(VoiceRecorderState.idle), messages: messages);
    await tester.pump(const Duration(milliseconds: 350));
    final list = find.byType(ListView).first;
    await tester.drag(list, const Offset(0, 220));
    await tester.pump();
    expect(find.byType(ChatJumpToLatestButton), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 2600));
    expect(find.byType(ChatJumpToLatestButton), findsNothing);

    await tester.drag(list, const Offset(0, 120));
    await tester.pump();
    expect(find.byType(ChatJumpToLatestButton), findsOneWidget);
  });

  testWidgets('successful memory writes show a receipt under the AI reply', (tester) async {
    final reply = ServerMessage(
      'reply-1',
      DateTime.utc(2026, 9, 27),
      'I will remember that.',
      MessageSender.ai,
      MessageType.text,
      null,
      false,
      [],
      [],
      [],
    )..memoryAction = 'saved';
    await pumpChat(tester, _VoiceState(VoiceRecorderState.idle), messages: [reply]);

    expect(find.text('Saved'), findsOneWidget);
    reply.memoryAction = 'updated';
    await pumpChat(tester, _VoiceState(VoiceRecorderState.idle), messages: [reply]);
    expect(find.text('Updated.'), findsOneWidget);
  });
}
