import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/models/voice_question_result.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _TestEnv implements EnvFields {
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

/// A tutorial voice question has a total response deadline. The production stream is an
/// async-generator chain over the HTTP body; when the body stalls, cancelling it waits for
/// the next chunk. The deadline must still settle on time, abort the in-flight request, and
/// never surface output that arrives afterwards. Transport is synthetic; no live provider.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    Env.init(_TestEnv());
    SharedPreferences.setMockInitialValues({'deviceIdHash': 'synthetic-device'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    Env.overrideApiBaseUrl('http://127.0.0.1:1/');
  });

  test('a stalled reply body cannot hold the voice deadline open, and the request is aborted', () async {
    final dir = await Directory.systemTemp.createTemp('voice-deadline');
    addTearDown(() => dir.delete(recursive: true));
    final audio = File('${dir.path}/synthetic.opus')..writeAsBytesSync([1, 2, 3]);

    final body = StreamController<List<int>>();
    final sent = Completer<http.BaseRequest>();
    final seams = ApiStreamingSeams(
      headers: (_) async => <String, String>{},
      transport: (request) {
        sent.complete(request);
        return Future.value(http.StreamedResponse(body.stream, 200));
      },
    );
    final provider = MessageProvider(
      voiceReplyTimeout: const Duration(milliseconds: 20),
      voiceAudioFileSaver: (_, __, ___) async => audio,
      voiceReplyStreamer: (files, {language, abort}) => sendVoiceMessageStreamServer(files, seams: seams, abort: abort),
    );
    addTearDown(provider.dispose);

    var settled = false;
    final operation = provider.sendVoiceMessageStreamToServer([
      [1]
    ], codec: BleAudioCodec.opus).whenComplete(() => settled = true);
    final request = await sent.future;
    await Future<void>.delayed(const Duration(milliseconds: 150));

    expect(settled, isTrue, reason: 'the deadline settles while the body is still stalled');
    expect(provider.showTypingIndicator, isFalse);
    expect(request, isA<http.Abortable>());
    var aborted = false;
    await (request as http.Abortable).abortTrigger!.timeout(const Duration(milliseconds: 50), onTimeout: () {});
    unawaited(request.abortTrigger!.then((_) => aborted = true));
    await Future<void>.delayed(Duration.zero);
    expect(aborted, isTrue, reason: 'the deadline aborts the in-flight request');

    // Output that arrives after the deadline is never shown.
    final shown = provider.messages.map((m) => m.text).join();
    body.add('data: late answer\n\n'.codeUnits);
    await body.close();
    await operation;
    await Future<void>.delayed(const Duration(milliseconds: 20));
    expect(provider.messages.map((m) => m.text).join(), shown);
  });

  test('stalled headers also settle on the deadline, and the next question still runs', () async {
    final dir = await Directory.systemTemp.createTemp('voice-deadline');
    addTearDown(() => dir.delete(recursive: true));
    final audio = File('${dir.path}/synthetic.opus')..writeAsBytesSync([1, 2, 3]);

    var calls = 0;
    final neverAnswers = Completer<http.StreamedResponse>();
    final seams = ApiStreamingSeams(
      headers: (_) async => <String, String>{},
      transport: (_) {
        calls++;
        return neverAnswers.future;
      },
    );
    final answered = StreamController<ServerMessageChunk>();
    final provider = MessageProvider(
      voiceReplyTimeout: const Duration(milliseconds: 20),
      voiceAudioFileSaver: (_, __, ___) async => audio,
      voiceReplyStreamer: (files, {language, abort}) =>
          calls == 0 ? sendVoiceMessageStreamServer(files, seams: seams, abort: abort) : answered.stream,
    );
    addTearDown(provider.dispose);

    await provider.sendVoiceMessageStreamToServer([
      [1]
    ], codec: BleAudioCodec.opus).timeout(const Duration(milliseconds: 150));
    expect(provider.showTypingIndicator, isFalse);

    // The busy guard was released: a new question is admitted rather than dropped as busy.
    final second = provider.sendVoiceMessageStreamToServer([
      [2]
    ], codec: BleAudioCodec.opus);
    await Future<void>.delayed(const Duration(milliseconds: 5));
    await answered.close();
    final result = await second.timeout(const Duration(milliseconds: 150));
    expect(result.failure, isNot(VoiceQuestionFailure.busy));
  });
}
