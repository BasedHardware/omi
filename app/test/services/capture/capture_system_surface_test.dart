import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/capture/capture_system_surface.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

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
    await world.settle();
    final pausedUpdates = sink.states.length;
    await world.elapse(const Duration(seconds: 12));
    expect(presentation.snapshot['elapsed'], elapsed);
    expect(sink.states.length, pausedUpdates, reason: 'Stop sends no updates while it lasts');
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
    await world.controller.pendingSourceSwitch; // Recovery first makes the WAL boundary durable.
    await world.settle();
    expect(presentation.snapshot['status'], isIn(['interrupted', 'connecting']));
    expect(presentation.snapshot['paused'], true);
    expect(presentation.snapshot['canPause'], true);
    expect(world.controller.isPaused, false);
  });

  test('a running card is republished at each full hour so its timer runs past it', () async {
    // A short Stop puts the hour mark between two 30 s health refreshes.
    await sink.action(request('pause'));
    await world.elapse(const Duration(seconds: 7));
    await sink.action(request('resume'));
    world.emitNativeState(PhoneMicCaptureState.running);
    final session = world.hostApi.lastStartSessionId!;
    final published = sink.states.length;
    // Audio every 2 s keeps the phone mic's 3 s stall check quiet for the hour.
    for (var frame = 40; (presentation.snapshot['elapsed'] as int) < 3630; frame += 20) {
      world.injectAudioFrames(20, sessionId: session, firstFrameIndex: frame);
      await world.elapse(const Duration(seconds: 2));
    }
    expect(presentation.snapshot['paused'], false);
    final pastHour = sink.states.skip(published).firstWhere((s) => (s['elapsed'] as int) >= 3600);
    expect(pastHour['elapsed'], 3600, reason: 'the update lands at the hour mark, not at the next refresh');
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

  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

  Future<void> recordWithPendant() async {
    await world.stopLiveCapture();
    world.deviceConnection = ScriptedDeviceConnection();
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
    expect(presentation.snapshot['source'], 'pendant');
  }

  test('silence timeout does not publish a false pause to the Live Activity', () async {
    await recordWithPendant();
    await world.elapse(const Duration(seconds: 120));
    await world.controller.pendingSourceSwitch;
    await world.settle();
    expect(presentation.snapshot['paused'], false);
    expect(presentation.snapshot['status'], 'listening');
    expect(presentation.snapshot['canPause'], true);
  });

  test('an Omi call holding the pendant reads as an interruption, without Stop or Start', () async {
    await recordWithPendant();
    world.omiCall.value = PhoneCallState.active;
    await world.controller.pendingSourceSwitch;
    await world.settle();
    expect(world.controller.pendantPausedForCall, isTrue);
    expect(presentation.snapshot['active'], true);
    expect(presentation.snapshot['status'], 'interrupted');
    expect(presentation.snapshot['paused'], true);
    expect(presentation.snapshot['canPause'], false);
    await expectLater(sink.action(request('resume')), throwsStateError);

    world.omiCall.value = PhoneCallState.ended;
    await world.controller.pendingSourceSwitch;
    await world.settle();
    expect(presentation.snapshot['paused'], false);
    expect(presentation.snapshot['canPause'], true);
  });

  test('a Stop queued behind a handoff does not pause the recording that takes over', () async {
    await recordWithPendant();
    final pendantRecording = presentation.snapshot['recordingId'];

    // The card still shows the pendant when Stop is tapped while the phone takes over.
    final start = world.controller.streamRecording();
    final rejected = expectLater(sink.action(request('pause')), throwsStateError);
    await start;
    world.emitNativeState(PhoneMicCaptureState.running);
    await world.settle();
    expect(presentation.snapshot['source'], 'phone');
    expect(presentation.snapshot['recordingId'], isNot(pendantRecording));
    expect(world.controller.isPaused, false, reason: 'the tap was for the pendant recording');
    await rejected;
  });

  test('a failed card action stays on the card until the recording changes', () async {
    world.emitNativeState(PhoneMicCaptureState.interrupted);
    await world.settle();
    await expectLater(sink.action(request('pause')), throwsStateError);
    await world.settle();
    expect(sink.states.last['actionFailed'], true);
    final published = sink.states.length;
    await world.elapse(const Duration(seconds: 30));
    expect(sink.states.length, greaterThan(published));
    expect(sink.states.last['status'], 'interrupted');
    expect(sink.states.last['actionFailed'], true, reason: 'a health refresh keeps the failure');

    world.emitNativeState(PhoneMicCaptureState.running);
    world.injectAudioFrames(20, sessionId: world.hostApi.lastStartSessionId!, firstFrameIndex: 20);
    await world.settle();
    expect(sink.states.last['paused'], false);
    expect(sink.states.last['actionFailed'], false);
  });

  test('a card tap still queued when capture shuts down fails instead of succeeding', () async {
    // The stop keeps the coordinator busy while the tap waits behind it.
    unawaited(world.controller.stopStreamRecording().then((_) {}, onError: (_) {}));
    final rejected = expectLater(
      sink.action(request('finish')),
      throwsA(isA<StateError>().having((e) => e.message, 'message', 'Recording changed')),
    );
    world.disposeController();
    await rejected;
  });

  test('Finish processes phone conversation and stops its native capture', () async {
    world.controller.segments.add(
      TranscriptSegment(
        id: 'segment',
        text: 'A recording to finish',
        speaker: 'SPEAKER_00',
        speakerId: 0,
        isUser: false,
        personId: null,
        start: 0,
        end: 1,
        translations: [],
      ),
    );
    final finish = request('finish');
    await sink.action(finish);
    await world.settle();
    expect(world.hostApi.nativeRecording, false);
    expect(presentation.snapshot['active'], false);
    expect(world.processCalls, 1);
    final finishedUpdates = sink.states.length;
    await world.elapse(const Duration(seconds: 3));
    expect(sink.states.length, finishedUpdates, reason: 'End cancels decorative animation updates');
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
    // The card's Finish is the live page's finishCapture: it always asks for
    // processing, and an empty result only clears the processing skeleton.
    expect(world.processCalls, 1);
  });

  test('Finish in phone batch mode stops without requesting live processing', () async {
    await world.stopLiveCapture();
    await SharedPreferencesUtil().saveBool('batchModeEnabled', true);
    await world.startLiveCapture();
    world.emitNativeState(PhoneMicCaptureState.running);
    world.emitBatchProgress(2);
    await world.settle();
    expect(presentation.snapshot['status'], 'recording');
    final beforeLoop = sink.states.length;
    await world.elapse(const Duration(milliseconds: 1600));
    expect(sink.states.length, beforeLoop, reason: 'the OS animates the wave without activity updates');
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

  test('silence and speech never send wave updates', () async {
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

    await audio(60, const Duration(milliseconds: 1600));
    final quiet = sink.states.length;
    final startedAt = presentation.snapshot['startedAt'];
    await audio(60, const Duration(milliseconds: 3200));
    expect(sink.states.length, quiet, reason: 'the OS keeps the wave moving through silence');

    await audio(9000, const Duration(milliseconds: 3200));
    expect(sink.states.length, quiet, reason: 'speech does not change the animation');

    await audio(60, const Duration(milliseconds: 3200));
    expect(sink.states.length, quiet);
    expect(presentation.snapshot['startedAt'], startedAt, reason: 'the OS draws the wave from the same start');
    expect(presentation.snapshot.keys, isNot(contains('levels')), reason: 'the card draws the design wave, not audio');
  });

  test('capture sends no wave updates, failures cannot stop capture, and closing cancels updates', () async {
    final before = sink.states.length;
    // Keep real audio arriving so the native liveness watchdog does not
    // intentionally transition capture into recovery during this timer test.
    for (var second = 0; second < 5; second++) {
      world.injectAudioFrames(20, sessionId: world.hostApi.lastStartSessionId!, firstFrameIndex: (second + 1) * 20);
      await world.elapse(const Duration(seconds: 1));
    }
    expect(sink.states.length, before, reason: 'the OS animates the wave on its own clock');
    sink.fail = true;
    await sink.action(request('pause'));
    await world.elapse(const Duration(seconds: 30));
    expect(presentation.snapshot['active'], true);
    await presentation.close();
    expect(sink.closed, true);
    sink.fail = false;
    final closedUpdates = sink.states.length;
    await world.elapse(const Duration(seconds: 3));
    expect(sink.states.length, closedUpdates);
  });
}
