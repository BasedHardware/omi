// The Lock Screen / Dynamic Island controls over a pendant capture, driven through the real
// CaptureController and its single-owner coordinator (replay world + scripted pendant link).
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/capture/capture_system_surface.dart';
import 'package:omi/services/capture/capture_voice_meter.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

class _Surface implements CaptureSystemSurfaceSink {
  late Future<Map<String, Object?>> Function(Map<String, Object?>) action;
  final states = <Map<String, Object?>>[];
  @override
  Future<void> start(Future<Map<String, Object?>> Function(Map<String, Object?>) action) async {
    this.action = action;
  }

  @override
  Future<void> publish(Map<String, Object?> state) async => states.add(state);

  @override
  Future<void> close() async {}
}

void main() {
  late Directory directory;
  late CaptureReplayWorld world;
  late CaptureSystemSurface presentation;
  late _Surface sink;
  late ScriptedDeviceConnection link;
  final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('omi_live_activity_pendant_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
    sink = _Surface();
    presentation = CaptureSystemSurface(world.controller, sink, now: world.clock.now);
    await presentation.start();
    link = ScriptedDeviceConnection();
    world.deviceConnection = link;
    await world.controller.streamDeviceRecording(device: pendant);
    await world.settle();
    for (var i = 0; i < 5; i++) {
      link.emitAudio();
    }
    await world.settle();
  });

  tearDown(() async {
    await presentation.close();
    await world.dispose();
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });

  Map<String, Object?> request(String action) => {
        'recordingId': presentation.snapshot['recordingId'],
        'conversationRevision': presentation.snapshot['conversationRevision'],
        'action': action,
      };

  void heard(String text) => world.controller.segments.add(TranscriptSegment(
        id: 'segment',
        text: text,
        speaker: 'SPEAKER_00',
        speakerId: 0,
        isUser: false,
        personId: null,
        start: 0,
        end: 1,
        translations: [],
      ));

  test('a live pendant shows as the pendant, with Pause and Finish', () async {
    expect(presentation.snapshot['active'], true);
    expect(presentation.snapshot['source'], 'pendant');
    expect(presentation.snapshot['canPause'], true);
    expect(presentation.snapshot['canFinish'], true);
  });

  test('Finish processes the conversation, pauses the pendant and closes the presentation', () async {
    heard('Something worth keeping');
    await sink.action(request('finish'));
    await world.settle();
    expect(world.processCalls, 1);
    expect(world.controller.isPaused, true, reason: 'the pendant stops listening');
    expect(presentation.snapshot['active'], false, reason: 'the island closes');
    await expectLater(sink.action(request('resume')), throwsStateError, reason: 'nothing left to control');
  });

  test('Finish before anything was heard still stops, with nothing to process', () async {
    expect(world.controller.segments, isEmpty);
    await sink.action(request('finish'));
    await world.settle();
    expect(world.processCalls, 0);
    expect(world.controller.isPaused, true);
    expect(presentation.snapshot['active'], false);
  });

  test('resuming the pendant in Omi brings the presentation back', () async {
    await sink.action(request('finish'));
    await world.settle();
    expect(presentation.snapshot['active'], false);

    await world.controller.resumeDeviceRecording();
    await world.settle();
    expect(world.controller.isPaused, false);
    expect(presentation.snapshot['active'], true);
    expect(presentation.snapshot['status'], isNot('paused'));
  });

  test('while the mic is on the island keeps a one-second beat, measured or not; muted it rests', () async {
    await presentation.close();
    presentation = CaptureSystemSurface(world.controller, sink,
        now: world.clock.now, voiceMeter: CaptureVoiceMeter(now: world.clock.now));
    await presentation.start();
    // The pendant streams, but its audio never reaches the meter (as when it cannot decode it).
    world.controller.systemSurfaceAudioTap = null;
    Future<void> stream(Duration duration) async {
      for (var t = Duration.zero; t < duration; t += const Duration(milliseconds: 100)) {
        link.emitAudio();
        await world.elapse(const Duration(milliseconds: 100));
      }
    }

    final start = sink.states.length;
    await stream(const Duration(seconds: 4));
    final beats = sink.states.skip(start).toList();
    expect(beats.length, inInclusiveRange(3, 5), reason: 'about one update a second while the mic is on');
    expect(beats.every((s) => (s['levels'] as List).isEmpty), isTrue, reason: 'nothing measured');
    final seconds = [for (final s in beats) s['elapsed'] as int];
    expect(seconds.toSet().length, seconds.length, reason: 'each beat carries a new second: the orb breathes on it');

    await sink.action(request('pause'));
    await world.settle();
    final settled = sink.states.length;
    await stream(const Duration(seconds: 3));
    expect(sink.states.length, settled, reason: 'muted, the island rests');
  });

  test('Pause and Resume from the island go through the capture owner', () async {
    await sink.action(request('pause'));
    await world.settle();
    expect(world.controller.isPaused, true);
    expect(presentation.snapshot['status'], 'paused');
    expect(presentation.snapshot['active'], true, reason: 'a pause keeps the card, with Resume');

    await sink.action(request('resume'));
    await world.settle();
    expect(world.controller.isPaused, false);
    expect(presentation.snapshot['status'], isNot('paused'));
  });
}
