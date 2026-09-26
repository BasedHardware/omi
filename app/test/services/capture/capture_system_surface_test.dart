import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/capture/capture_system_surface.dart';
import 'package:omi/services/capture/capture_voice_meter.dart';

import '../../support/capture/capture_replay_world.dart';

class _Surface implements CaptureSystemSurfaceSink {
  late Future<Map<String, Object?>> Function(Map<String, Object?>) action;
  final states = <Map<String, Object?>>[];
  bool closed = false;
  bool fail = false;
  @override
  Future<void> start(Future<Map<String, Object?>> Function(Map<String, Object?>) action) async {
    this.action = action;
  }

  @override
  Future<void> publish(Map<String, Object?> state) async {
    if (fail) throw StateError('Presentation unavailable');
    states.add(state);
  }

  @override
  Future<void> close() async {
    closed = true;
  }
}

void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  late CaptureSystemSurface presentation;
  late _Surface sink;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('omi_live_activity_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
    sink = _Surface();
    presentation = CaptureSystemSurface(world.controller, sink, now: world.clock.now);
    await presentation.start();
    await world.startLiveCapture();
    world.emitNativeState(PhoneMicCaptureState.running);
    world.injectAudioFrames(20, sessionId: world.hostApi.lastStartSessionId!);
    await world.settle();
  });

  tearDown(() async {
    await presentation.close();
    await world.dispose();
    directory.deleteSync(recursive: true);
  });

  Map<String, Object?> request(String action) => {
        'recordingId': presentation.snapshot['recordingId'],
        'conversationRevision': presentation.snapshot['conversationRevision'],
        'action': action,
      };

  test('phone pause fences real audio and resume preserves recording and elapsed time', () async {
    final id = presentation.snapshot['recordingId'];
    expect(presentation.snapshot['active'], true);
    await world.elapse(const Duration(seconds: 5));
    final before = world.socket!.sentBinary.length;
    final previousNativeSession = world.hostApi.lastStartSessionId!;
    await sink.action(request('pause'));
    world.injectAudioFrames(20, sessionId: previousNativeSession, firstFrameIndex: 20);
    await world.settle();
    expect(world.socket!.sentBinary.length, before);
    expect(presentation.snapshot['paused'], true);
    final elapsed = presentation.snapshot['elapsed'];
    await world.elapse(const Duration(seconds: 12));
    expect(presentation.snapshot['elapsed'], elapsed);
    final resumeIndex = sink.states.length;
    await sink.action(request('resume'));
    world.emitNativeState(PhoneMicCaptureState.running);
    world.injectAudioFrames(20, sessionId: world.hostApi.lastStartSessionId!, firstFrameIndex: 40);
    await world.settle();
    expect(presentation.snapshot['recordingId'], id);
    expect(world.socket!.sentBinary.length, greaterThan(before));
    expect(presentation.snapshot['paused'], false);
    expect(sink.states.skip(resumeIndex).every((s) => s['active'] == true), true);
    await world.elapse(const Duration(seconds: 3));
    expect(presentation.snapshot['elapsed'], (elapsed as int) + 3);
  });

  test('a repeated Pause does not issue a second mute intent', () async {
    final pause = request('pause');
    await sink.action(pause);
    final revision = SharedPreferencesUtil().capturePolicy.revision;
    await sink.action(pause);
    expect(SharedPreferencesUtil().capturePolicy.revision, revision);
  });

  test('old recording action cannot pause the next recording', () async {
    final old = request('pause');
    await world.stopLiveCapture();
    await world.startLiveCapture();
    world.emitNativeState(PhoneMicCaptureState.running);
    await world.settle();
    expect(presentation.snapshot['recordingId'], isNot(old['recordingId']));
    await expectLater(sink.action(old), throwsStateError);
    expect(world.controller.isPaused, false);
  });

  test('star is not a system surface action', () async {
    expect(presentation.snapshot.containsKey('canStar'), false);
    await expectLater(sink.action(request('star')), throwsStateError);
    expect(world.controller.isConversationMarkedForStarring, false);
  });

  test('stall recovery is not shown as a user pause and keeps Pause available', () async {
    await world.elapse(const Duration(seconds: 5));
    expect(presentation.snapshot['status'], isIn(['interrupted', 'connecting']));
    expect(presentation.snapshot['paused'], true);
    expect(presentation.snapshot['canPause'], true);
    expect(world.controller.isPaused, false);
  });

  test('user pause offers Resume; a call interruption freezes without offering it', () async {
    await sink.action(request('pause'));
    expect(presentation.snapshot['status'], 'paused');
    expect(presentation.snapshot['canPause'], true);
    await sink.action(request('resume'));
    world.emitNativeState(PhoneMicCaptureState.running);
    world.injectAudioFrames(20, sessionId: world.hostApi.lastStartSessionId!, firstFrameIndex: 20);
    await world.settle();

    world.emitNativeState(PhoneMicCaptureState.interrupted);
    await world.settle();
    expect(presentation.snapshot['status'], 'interrupted');
    expect(presentation.snapshot['paused'], true);
    expect(presentation.snapshot['canPause'], false);
    expect(presentation.snapshot['canFinish'], true);
    await expectLater(sink.action(request('resume')), throwsStateError);
  });

  test('Finish processes phone conversation and stops its native capture', () async {
    world.controller.segments.add(TranscriptSegment(
      id: 'segment',
      text: 'A recording to finish',
      speaker: 'SPEAKER_00',
      speakerId: 0,
      isUser: false,
      personId: null,
      start: 0,
      end: 1,
      translations: [],
    ));
    final finish = request('finish');
    await sink.action(finish);
    await world.settle();
    expect(world.hostApi.nativeRecording, false);
    expect(presentation.snapshot['active'], false);
    expect(world.processCalls, 1);
    await expectLater(sink.action(finish), throwsStateError);
    expect(world.processCalls, 1);
  });

  test('Finish can stop phone capture before the first transcript arrives', () async {
    expect(world.controller.segments, isEmpty);
    expect(presentation.snapshot['canFinish'], true);
    await sink.action(request('finish'));
    await world.settle();
    expect(world.hostApi.nativeRecording, false);
    expect(presentation.snapshot['active'], false);
    expect(world.processCalls, 0);
  });

  test('Finish in phone batch mode stops without requesting live processing', () async {
    await world.stopLiveCapture();
    await SharedPreferencesUtil().saveBool('batchModeEnabled', true);
    await world.startLiveCapture();
    world.emitNativeState(PhoneMicCaptureState.running);
    world.emitBatchProgress(2);
    await world.settle();
    expect(presentation.snapshot['batch'], true);
    await sink.action(request('finish'));
    await world.settle();
    expect(world.hostApi.nativeRecording, false);
    expect(presentation.snapshot['active'], false);
    expect(world.processCalls, 0);
  });

  test('processing a conversation preserves continuous capture and rejects old card actions', () async {
    final id = presentation.snapshot['recordingId'];
    final oldAction = request('pause');
    world.clock.advanceTo(world.clock.now().add(const Duration(seconds: 10)));
    expect(presentation.snapshot['elapsed'], 10);
    // The pendant Finish path uses this same conversation processing operation.
    await world.controller.forceProcessingCurrentConversation();
    await world.settle();
    expect(presentation.snapshot['recordingId'], id);
    expect(presentation.snapshot['active'], true);
    expect(presentation.snapshot['elapsed'], 0);
    expect(world.hostApi.nativeRecording, true);
    expect(world.processCalls, 1);
    await expectLater(sink.action(oldAction), throwsStateError);
  });

  test('while audio flows the waveform moves about once a second; voice rises above a soft idle wave', () async {
    await presentation.close();
    presentation = CaptureSystemSurface(world.controller, sink,
        now: world.clock.now, voiceMeter: CaptureVoiceMeter(now: world.clock.now));
    await presentation.start();
    final session = world.hostApi.lastStartSessionId!;
    Future<void> audio(double amplitude, Duration duration) async {
      for (var t = Duration.zero; t < duration; t += const Duration(milliseconds: 100)) {
        final data = ByteData(3200);
        for (var i = 0; i < 1600; i++) {
          data.setInt16(i * 2, (amplitude * math.sin(i * 0.3)).round(), Endian.little);
        }
        world.mic.onAudioFrame(data.buffer.asUint8List(), session);
        await world.elapse(const Duration(milliseconds: 100));
      }
    }

    // A quiet room: the strip keeps moving with the soft idle wave, well below speech.
    final start = sink.states.length;
    await audio(60, const Duration(seconds: 3));
    final quiet = sink.states.skip(start).where((s) => (s['levels'] as List).isNotEmpty).toList();
    expect(quiet.length, inInclusiveRange(2, 4), reason: 'a quiet room keeps a soft wave moving');
    expect(quiet.last['voice'], false);
    expect((quiet.last['levels'] as List<int>).reduce(math.max), lessThanOrEqualTo(26));

    final before = sink.states.length;
    await audio(9000, const Duration(seconds: 3));
    final voiced = sink.states.skip(before).where((s) => s['voice'] == true).toList();
    expect(voiced.length, inInclusiveRange(2, 4));
    expect(voiced.last['levels'], hasLength(CaptureVoiceMeter.history));
    expect((voiced.last['levels'] as List).last, greaterThan(50));

    // Pausing settles the strip with one update, then the surface goes quiet.
    await sink.action(request('pause'));
    await audio(60, const Duration(seconds: 2));
    expect(sink.states.last['levels'], isEmpty);
    final settled = sink.states.length;
    await audio(60, const Duration(seconds: 3));
    expect(sink.states.length, settled);
  });

  test('the idle wave stays between 8 and 26 and keeps each bar as the strip slides', () {
    final levels = [for (var bin = 0; bin < 400; bin++) CaptureSystemSurface.idleLevel(bin)];
    expect(levels.reduce(math.min), greaterThanOrEqualTo(8));
    expect(levels.reduce(math.max), lessThanOrEqualTo(26));
    // Keyed by absolute bin: the same bin always has the same height.
    expect(CaptureSystemSurface.idleLevel(123), CaptureSystemSurface.idleLevel(123));
    // Real loudness wins over the idle floor.
    expect(CaptureSystemSurface.blendIdle([90, 0], 11), [90, CaptureSystemSurface.idleLevel(11)]);
  });

  test('a failing presentation tap never drops audio from capture', () async {
    world.controller.systemSurfaceAudioTap = (_, __) => throw StateError('meter failed');
    final before = world.socket!.sentBinary.length;
    world.injectAudioFrames(20, sessionId: world.hostApi.lastStartSessionId!, firstFrameIndex: 20);
    await world.settle();
    expect(world.socket!.sentBinary.length, greaterThan(before));
  });

  test('closing the surface detaches the audio tap', () async {
    await presentation.close();
    presentation = CaptureSystemSurface(world.controller, sink,
        now: world.clock.now, voiceMeter: CaptureVoiceMeter(now: world.clock.now));
    await presentation.start();
    expect(world.controller.systemSurfaceAudioTap, isNotNull);
    await presentation.close();
    expect(world.controller.systemSurfaceAudioTap, isNull);
  });

  test('OS updates do not tick every second and failures do not stop capture', () async {
    final before = sink.states.length;
    // Keep real audio arriving so the native liveness watchdog does not
    // intentionally transition capture into recovery during this timer test.
    for (var second = 0; second < 5; second++) {
      world.injectAudioFrames(20, sessionId: world.hostApi.lastStartSessionId!, firstFrameIndex: (second + 1) * 20);
      await world.elapse(const Duration(seconds: 1));
    }
    expect(sink.states.length, before);
    sink.fail = true;
    await sink.action(request('pause'));
    await world.elapse(const Duration(seconds: 30));
    expect(presentation.snapshot['active'], true);
    await presentation.close();
    expect(sink.closed, true);
  });
}
