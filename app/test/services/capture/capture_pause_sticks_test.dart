// The reader's two controls over a pendant: Mute holds until Unmute, and Stop holds until Start —
// through a pendant dropping and reconnecting, an app restart, and a phone recording that borrowed
// the capture. The real CaptureController and its coordinator over the replay world, with a
// scripted pendant link.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/utils/enums.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  late ScriptedDeviceConnection link;
  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_pause_sticks_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
    link = ScriptedDeviceConnection();
    world.deviceConnection = link;
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
  });

  tearDown(() async {
    await world.dispose();
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });

  /// Bytes the current socket receives when the pendant sends [packets] packets (0 when paused).
  Future<int> pendantBytesReaching({int packets = 5}) async {
    final socket = world.socket;
    if (socket == null) return 0;
    final before = socket.sentBinary.length;
    for (var i = 0; i < packets; i++) {
      link.emitAudio();
    }
    await world.settle();
    return socket.sentBinary.length - before;
  }

  void heard(String text) => world.controller.segments.add(TranscriptSegment(
        id: 'segment-${world.controller.segments.length}',
        text: text,
        speaker: 'SPEAKER_00',
        speakerId: 0,
        isUser: false,
        personId: null,
        start: 0,
        end: 1,
        translations: [],
      ));

  test('a live pendant streams, and a pause stops the audio', () async {
    expect(await pendantBytesReaching(), greaterThan(0));
    await world.controller.pauseDeviceRecording();
    await world.settle();
    expect(world.controller.isPaused, true);
    expect(await pendantBytesReaching(), 0);
  });

  test('a paused pendant that drops and reconnects stays paused', () async {
    await world.controller.pauseDeviceRecording();
    await world.settle();

    world.controller.updateRecordingDevice(null);
    await world.settle();
    world.controller.updateRecordingDevice(pendant);
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();

    expect(world.controller.isPaused, true);
    expect(world.controller.recordingState, isNot(RecordingState.deviceRecord));
    expect(await pendantBytesReaching(), 0, reason: 'no audio is captured until the reader resumes');
  });

  test('a paused pendant stays paused after the app restarts', () async {
    await world.controller.pauseDeviceRecording();
    await world.settle();

    await world.reconstructProcess();
    world.deviceConnection = link;
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();

    expect(world.controller.isPaused, true);
    expect(await pendantBytesReaching(), 0);
  });

  test('a phone recording that took over from a paused pendant hands it back paused', () async {
    await world.controller.pauseDeviceRecording();
    await world.settle();

    await world.controller.streamRecording();
    world.emitNativeState(PhoneMicCaptureState.running);
    await world.settle();
    expect(world.controller.liveCaptureSource, 'phone');

    await world.controller.stopStreamRecording();
    await world.settle();
    expect(world.controller.isPaused, true, reason: 'the pendant goes back to how the reader left it');
    expect(await pendantBytesReaching(), 0);
  });

  test('the capture API alone finishes a conversation and keeps a pendant listening', () async {
    await world.controller.finishCapture();
    await world.settle();
    expect(world.controller.isPaused, false);
    expect(await pendantBytesReaching(), greaterThan(0));
  });

  test('Stop saves what was heard and stops the pendant; Start listens again', () async {
    heard('Something worth keeping');
    final saved = await world.controller.stopCapture();
    await world.settle();
    expect(saved, true, reason: 'the caller shows it in Conversations');
    expect(world.processCalls, 1);
    expect(world.controller.isCaptureStopped, true);
    expect(await pendantBytesReaching(), 0, reason: 'no next conversation starts by itself');

    await world.controller.startCapture();
    await world.settle();
    expect(world.controller.isCaptureStopped, false);
    expect(world.controller.isPaused, false);
    expect(await pendantBytesReaching(), greaterThan(0));
    await world.elapse(const Duration(seconds: 5));
    expect(world.controller.isPaused, false, reason: 'Start sticks');
    expect(await pendantBytesReaching(), greaterThan(0));
  });

  test('Stop with nothing heard saves nothing, and still stops', () async {
    final saved = await world.controller.stopCapture();
    await world.settle();
    expect(saved, false, reason: 'the caller goes back to Today');
    expect(world.processCalls, 0);
    expect(world.controller.isCaptureStopped, true);
    expect(await pendantBytesReaching(), 0);
  });

  test('Mute is not Stop: the conversation stays open and Unmute carries on', () async {
    heard('First half');
    await world.controller.pauseCapture();
    await world.settle();
    expect(world.controller.isPaused, true);
    expect(world.controller.isCaptureStopped, false);
    expect(world.processCalls, 0, reason: 'muting saves nothing yet');
    expect(world.controller.segments, isNotEmpty);

    await world.controller.resumeCapture();
    await world.settle();
    expect(world.controller.isPaused, false);
    expect(world.controller.segments, isNotEmpty, reason: 'the same conversation');
    expect(await pendantBytesReaching(), greaterThan(0));
  });

  test('a stop holds through the pendant reconnecting and an app restart', () async {
    await world.controller.stopCapture();
    await world.settle();

    world.controller.updateRecordingDevice(null);
    await world.settle();
    world.controller.updateRecordingDevice(pendant);
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
    expect(world.controller.isCaptureStopped, true);
    expect(await pendantBytesReaching(), 0);

    await world.reconstructProcess();
    world.deviceConnection = link;
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
    expect(world.controller.isCaptureStopped, true, reason: 'still waiting for Start');
    expect(await pendantBytesReaching(), 0);

    await world.controller.startCapture();
    await world.settle();
    expect(world.controller.isCaptureStopped, false);
    expect(await pendantBytesReaching(), greaterThan(0));
  });

  test("the pendant's double tap unmutes a stop too (listening again is never stopped)", () async {
    await world.controller.stopCapture();
    await world.settle();
    await world.controller.resumeDeviceRecording();
    await world.settle();
    expect(world.controller.isCaptureStopped, false);
    expect(world.controller.isPaused, false);
  });

  test('one clock: it stands still while muted and starts from zero after Stop and Start', () async {
    await world.elapse(const Duration(seconds: 30));
    final listened = world.controller.captureElapsed!;
    expect(listened.inSeconds, greaterThanOrEqualTo(30));

    await world.controller.pauseCapture();
    await world.settle();
    await world.elapse(const Duration(seconds: 20));
    expect(world.controller.captureElapsed!.inSeconds, listened.inSeconds, reason: 'muted time does not count');

    await world.controller.resumeCapture();
    await world.settle();
    await world.elapse(const Duration(seconds: 10));
    expect(world.controller.captureElapsed!.inSeconds, listened.inSeconds + 10);

    await world.controller.stopCapture();
    await world.settle();
    await world.elapse(const Duration(seconds: 15));
    await world.controller.startCapture();
    await world.settle();
    await world.elapse(const Duration(seconds: 4));
    expect(world.controller.captureElapsed!.inSeconds, inInclusiveRange(4, 5), reason: 'a new conversation');
  });
}
