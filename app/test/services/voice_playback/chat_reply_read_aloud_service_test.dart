import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/voice_playback/chat_reply_read_aloud.dart';
import 'package:omi/services/voice_playback/omi_voice_playback_service.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

final _mp3 = Uint8List.fromList(const [1, 2, 3]);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late OmiVoicePlaybackService service;
  late List<String> synthesized;
  Completer<VoicePlaybackOutputSnapshot>? probeGate;

  VoicePlaybackOutputSnapshot output({bool headphones = true, bool failed = false}) => VoicePlaybackOutputSnapshot(
        headphonesConnected: headphones,
        checkFailed: failed,
        route: headphones ? VoiceReplyPlaybackOutputRoute.bluetooth : VoiceReplyPlaybackOutputRoute.speaker,
      );

  void install({VoicePlaybackOutputSnapshot? snapshot, bool gateProbe = false}) {
    service.debugHooks = VoicePlaybackDebugHooks(
      synthesize: ({required String text, String? voiceId}) async {
        synthesized.add(text);
        return _mp3;
      },
      play: (bytes) async {},
      stopPlayback: () async {},
      speak: (text) async {},
      stopSpeak: () async {},
      probeOutput: () {
        if (gateProbe) {
          probeGate = Completer<VoicePlaybackOutputSnapshot>();
          return probeGate!.future;
        }
        return Future.value(snapshot ?? output());
      },
    );
  }

  ChatReplyReadAloud coordinator({bool enabled = true}) {
    var serial = 0;
    return ChatReplyReadAloud(
      isEnabled: () => enabled && SharedPreferencesUtil().readChatRepliesAloud,
      playbackId: () => 'chat:${serial++}',
    )..active = true;
  }

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({'uid': 'uid-a'});
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.0.543',
      buildNumber: '992',
      buildSignature: '',
    );
    await SharedPreferencesUtil.init();
    service = OmiVoicePlaybackService.instance;
    service.debugReset();
    synthesized = [];
    probeGate = null;
    SharedPreferencesUtil().readChatRepliesAloud = true;
  });

  tearDown(() {
    service.debugReset();
    AnalyticsManager.resetForTesting();
  });

  test('enabled + mode Off never synthesizes', () async {
    SharedPreferencesUtil().voiceResponseMode = 0;
    install();
    final readAloud = coordinator();
    await readAloud.readFinalReply('A complete reply for the user.', generation: readAloud.generation);
    await pumpEventQueue();
    expect(synthesized, isEmpty);
  });

  test('enabled + headphones-only mode without headphones stays silent', () async {
    SharedPreferencesUtil().voiceResponseMode = 1;
    install(snapshot: output(headphones: false));
    final readAloud = coordinator();
    await readAloud.readFinalReply('A complete reply for the user.', generation: readAloud.generation);
    await pumpEventQueue();
    expect(synthesized, isEmpty);
  });

  test('enabled + headphones-only mode with a failed probe fails closed', () async {
    SharedPreferencesUtil().voiceResponseMode = 1;
    install(snapshot: output(headphones: false, failed: true));
    final readAloud = coordinator();
    await readAloud.readFinalReply('A complete reply for the user.', generation: readAloud.generation);
    await pumpEventQueue();
    expect(synthesized, isEmpty);
  });

  test('enabled + headphones present speaks the final reply once', () async {
    SharedPreferencesUtil().voiceResponseMode = 1;
    install();
    final readAloud = coordinator();
    await readAloud.readFinalReply(
      'This final answer is long enough to reach the first chunk threshold and then some more.',
      generation: readAloud.generation,
    );
    await pumpEventQueue();
    expect(synthesized, hasLength(1));
  });

  test('enabled + always mode speaks through the speaker', () async {
    SharedPreferencesUtil().voiceResponseMode = 2;
    install(snapshot: output(headphones: false));
    final readAloud = coordinator();
    await readAloud.readFinalReply(
      'This final answer is long enough to reach the first chunk threshold and then some more.',
      generation: readAloud.generation,
    );
    await pumpEventQueue();
    expect(synthesized, hasLength(1));
  });

  test('a revoked chat begin in-flight cannot supersede a newer pendant reply', () async {
    SharedPreferencesUtil().voiceResponseMode = 2;
    install(gateProbe: true);
    final readAloud = coordinator();
    final pending = readAloud.readFinalReply('A chat reply.', generation: readAloud.generation);
    await pumpEventQueue();
    expect(probeGate, isNotNull);

    readAloud.revoke();
    install();
    await service.beginResponse(messageId: 'pendant:turn-1');
    service.updateStreamingResponse(
      messageId: 'pendant:turn-1',
      fullText: 'Pendant answer that is long enough to reach the first chunk threshold easily.',
      isFinal: true,
    );

    probeGate!.complete(output());
    await pending;
    await pumpEventQueue();
    expect(synthesized, hasLength(1));

    service.updateStreamingResponse(
      messageId: 'chat:0',
      fullText: 'Revoked chat reply that must never synthesize audio for the user at all.',
      isFinal: true,
    );
    await pumpEventQueue();
    expect(synthesized, hasLength(1));
  });
}
