// One live source at a time (David, 2026-09-25): the pendant, the phone mic and an Omi call never
// capture together, a pause keeps its conversation, and a source that another one paused comes
// back on its own. Each scenario drives the real CaptureController over the replay world.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/utils/enums.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_one_source_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
  });

  tearDown(() async {
    await world.dispose();
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });

  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

  Future<ScriptedDeviceConnection> connectPendant() async {
    final link = ScriptedDeviceConnection();
    world.deviceConnection = link;
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
    return link;
  }

  /// Bytes the current socket receives when the pendant sends [packets] packets.
  Future<int> pendantBytesReaching(ScriptedDeviceConnection link, {int packets = 5}) async {
    final socket = world.socket!;
    final before = socket.sentBinary.length;
    for (var i = 0; i < packets; i++) {
      link.emitAudio();
    }
    await world.settle();
    return socket.sentBinary.length - before;
  }

  Future<void> callSwitch() async {
    await world.controller.pendingSourceSwitch;
    await world.settle();
  }

  Future<int> startPhone() async {
    await world.startLiveCapture();
    world.emitNativeState(PhoneMicCaptureState.running);
    await world.settle();
    return world.hostApi.lastStartSessionId!;
  }

  group('(a) a phone pause keeps one conversation', () {
    test('pause then resume keeps the recording id, the socket and the transcript', () async {
      final session = await startPhone();
      world.injectAudioFrames(20, sessionId: session);
      await world.settle();
      final c = world.controller;
      final recording = c.activeRecordingId;
      final sockets = world.sockets.length;

      await c.pauseCapture();
      await world.settle();
      expect(c.isPaused, isTrue);
      expect(c.recordingState, RecordingState.pause);

      await c.resumeCapture();
      await world.settle();
      world.emitNativeState(PhoneMicCaptureState.running);
      final before = world.socket!.sentBinary.length;
      world.injectAudioFrames(20, sessionId: world.hostApi.lastStartSessionId!, firstFrameIndex: 20);
      await world.settle();

      expect(c.activeRecordingId, recording, reason: 'a new recording id is a new conversation on /v4/listen');
      expect(world.sockets.length, sockets, reason: 'resume must reuse the open socket');
      expect(world.socket!.sentBinary.length, greaterThan(before));
      expect(c.isPaused, isFalse);
      expect(c.recordingState, RecordingState.record);
    });

    test('audio captured while paused never reaches the socket', () async {
      final session = await startPhone();
      final c = world.controller;
      await c.pauseCapture();
      await world.settle();
      final before = world.socket!.sentBinary.length;
      world.injectAudioFrames(20, sessionId: session, firstFrameIndex: 100);
      await world.settle();
      expect(world.socket!.sentBinary.length, before);
    });
  });

  group('(b) stopping the phone does not pause anything else', () {
    test('after a phone recording stops, capture is not left paused', () async {
      await startPhone();
      await world.stopLiveCapture();
      expect(world.controller.isPaused, isFalse);
    });

    test('a pendant that connects after a phone recording streams, not paused', () async {
      await startPhone();
      await world.stopLiveCapture();
      final link = await connectPendant();
      expect(world.controller.recordingState, RecordingState.deviceRecord);
      expect(await pendantBytesReaching(link), greaterThan(0));
    });
  });

  group('(c) the phone takes over from a live pendant explicitly', () {
    test('while the phone records, pendant audio never reaches the phone socket', () async {
      final link = await connectPendant();
      expect(await pendantBytesReaching(link), greaterThan(0), reason: 'the pendant streams before the switch');
      final pendantRecording = world.controller.activeRecordingId;

      await startPhone();
      expect(world.controller.activeRecordingId, isNot(pendantRecording),
          reason: 'the phone recording is its own conversation, not a continuation of the pendant\'s');
      expect(world.sockets.last.source, isNot('omi'), reason: 'the phone opens its own socket');
      expect(link.openAudioSubscriptions, 0, reason: 'the pendant stream is paused during the phone recording');
      expect(await pendantBytesReaching(link), 0);
    });

    test('when the phone recording stops, the pendant resumes by itself', () async {
      final link = await connectPendant();
      await startPhone();
      await world.stopLiveCapture();

      final c = world.controller;
      expect(c.isPaused, isFalse);
      expect(c.recordingState, RecordingState.deviceRecord);
      expect(link.openAudioSubscriptions, 1);
      expect(world.sockets.last.source, isNot('phone'));
      expect(await pendantBytesReaching(link), greaterThan(0));
    });

    test('Finish processes the phone conversation before the pendant resumes', () async {
      final link = await connectPendant();
      await startPhone();
      int? pendantStreamsAtProcess;
      world.onProcessInProgress = () => pendantStreamsAtProcess = link.openAudioSubscriptions;

      await world.controller.finishCapture();
      await world.settle();

      expect(world.processCalls, 1);
      expect(pendantStreamsAtProcess, 0, reason: 'the pendant must not open its next conversation first');
      expect(link.openAudioSubscriptions, 1);
      expect(world.controller.pendantPausedForPhone, isFalse);
    });

    test('a pendant that connects during a phone recording waits for it', () async {
      await startPhone();
      final socketsBefore = world.sockets.length;
      final link = await connectPendant();

      expect(world.controller.pendantPausedForPhone, isTrue);
      expect(link.openAudioSubscriptions, 0);
      expect(world.sockets.length, socketsBefore, reason: 'the phone keeps its socket');
      expect(world.controller.recordingState, RecordingState.record);

      await world.stopLiveCapture();
      expect(link.openAudioSubscriptions, 1);
      expect(world.controller.recordingState, RecordingState.deviceRecord);
    });

    test('a pendant that disconnects during the phone recording is not resumed', () async {
      await connectPendant();
      await startPhone();
      world.controller.updateRecordingDevice(null);
      await world.stopLiveCapture();

      expect(world.controller.pendantPausedForPhone, isFalse);
      expect(world.controller.isPaused, isFalse);
      expect(world.controller.recordingState, RecordingState.stop);
    });

    test('a pendant the user had paused stays paused after the phone recording', () async {
      final link = await connectPendant();
      await world.controller.pauseCapture();
      await world.settle();
      await startPhone();
      await world.stopLiveCapture();

      expect(world.controller.isPaused, isTrue);
      expect(world.controller.recordingState, RecordingState.pause);
      expect(link.openAudioSubscriptions, 0);
    });
  });

  group('pause survives the paths that used to restart or strand it', () {
    test('turning Transcribe Later on while paused keeps the paused recording resumable', () async {
      final session = await startPhone();
      final c = world.controller;
      final recording = c.activeRecordingId;
      await c.pauseCapture();
      await world.settle();
      await c.setBatchMode(true);
      await world.settle();
      expect(c.isPhoneMicPaused, isTrue);

      await c.resumeCapture();
      await world.settle();
      world.emitNativeState(PhoneMicCaptureState.running);
      world.injectAudioFrames(10, sessionId: world.hostApi.lastStartSessionId!, firstFrameIndex: 50);
      await world.settle();
      expect(c.activeRecordingId, recording);
      expect(c.recordingState, RecordingState.record);
      expect(session, isNot(world.hostApi.lastStartSessionId), reason: 'only the mic restarted');
    });

    test('a process death during a phone pause does not leave the next launch muted', () async {
      await startPhone();
      await world.controller.pauseCapture();
      await world.settle();
      expect(world.controller.isPaused, isTrue);

      world.killProcess();
      await world.reconstructProcess();
      expect(world.controller.isPaused, isFalse);
    });
  });

  group('the live source the UI shows', () {
    test('names the phone, including while paused, and the pendant otherwise', () async {
      final c = world.controller;
      expect(c.liveCaptureSource, isNull);
      await connectPendant();
      expect(c.liveCaptureSource, 'omi');
      await startPhone();
      expect(c.liveCaptureSource, 'phone', reason: 'the pendant is connected but handed off');
      expect(c.liveCaptureStartedAt, isNotNull);
      await c.pauseCapture();
      await world.settle();
      expect(c.liveCaptureSource, 'phone');
      await c.finishCapture();
      await world.settle();
      expect(c.liveCaptureSource, 'omi');
    });
  });

  group('(d) an Omi call pauses the pendant and gives it back', () {
    test('pendant audio stops during the call and flows again after it', () async {
      final link = await connectPendant();
      expect(await pendantBytesReaching(link), greaterThan(0));

      world.omiCall.value = PhoneCallState.active;
      await callSwitch();
      expect(world.controller.pendantPausedForCall, isTrue);
      expect(link.openAudioSubscriptions, 0);
      expect(await pendantBytesReaching(link), 0);

      world.omiCall.value = PhoneCallState.ended;
      await callSwitch();
      expect(link.openAudioSubscriptions, 1);
      expect(world.controller.recordingState, RecordingState.deviceRecord);
      expect(await pendantBytesReaching(link), greaterThan(0));
    });

    test('a pendant that drops and reconnects during the call stays off, with its transcript', () async {
      final link = await connectPendant();
      world.omiCall.value = PhoneCallState.active;
      await callSwitch();
      final recording = world.controller.activeRecordingId;

      world.controller.updateRecordingDevice(null);
      await world.controller.streamDeviceRecording(device: pendant);
      await world.settle();

      expect(world.controller.pendantPausedForCall, isTrue);
      expect(link.openAudioSubscriptions, 0);
      expect(world.controller.activeRecordingId, recording, reason: 'the reconnect must not start a new session');

      world.omiCall.value = PhoneCallState.idle;
      await callSwitch();
      expect(link.openAudioSubscriptions, 1);
    });

    test('a call that ends while the phone takes over does not resume the pendant under it', () async {
      final link = await connectPendant();
      world.omiCall.value = PhoneCallState.active;
      await startPhone();
      world.omiCall.value = PhoneCallState.idle;
      await callSwitch();
      expect(link.openAudioSubscriptions, 0, reason: 'the phone still owns the capture');
      await world.stopLiveCapture();
      await callSwitch();
      expect(link.openAudioSubscriptions, 1);
    });

    test('a call does not unpause a pendant the user paused', () async {
      final link = await connectPendant();
      await world.controller.pauseCapture();
      await world.settle();
      world.omiCall.value = PhoneCallState.active;
      await callSwitch();
      world.omiCall.value = PhoneCallState.idle;
      await callSwitch();
      expect(world.controller.isPaused, isTrue);
      expect(link.openAudioSubscriptions, 0);
    });
  });
}
