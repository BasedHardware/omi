// Live phone-mic audio stays in the phone's WAL until the server's transcript confirms it, as pendant
// audio does (#20366). A socket send is not a save. These scenarios drive the real CaptureController,
// native mic service and LocalWalSyncImpl over the replay world.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal.dart';

import '../../support/capture/capture_replay_world.dart';

void main() {
  late Directory directory;
  late CaptureReplayWorld world;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture_phone_backup_');
    world = await CaptureReplayWorld.boot(tempDir: directory);
  });

  tearDown(() async {
    await world.dispose();
    if (directory.existsSync()) directory.deleteSync(recursive: true);
  });

  /// Finalize, stamp and confirm write real files outside the virtual scheduler, so let real time
  /// pass until the WAL index stops changing.
  Future<void> settleFiles() async {
    var last = '';
    for (var i = 0; i < 40; i++) {
      await world.settle();
      await Future<void>.delayed(const Duration(milliseconds: 50));
      final wals = await world.wal.syncs.phone.getAllWals();
      final now = [
        for (final wal in wals) '${wal.id}:${wal.status.name}:${wal.conversationId}',
        'uploads=${world.uploads.attempts.length}',
      ].join(',');
      if (now == last && i >= 3) return;
      last = now;
    }
  }

  /// Waits, in real time, until [done] holds for the phone's WALs. Writing, stamping and releasing
  /// copies touch real files outside the virtual scheduler, so a quiet moment does not prove they are done.
  Future<List<Wal>> walsReach(bool Function(List<Wal> wals) done) async {
    for (var i = 0; i < 200; i++) {
      final wals = await world.wal.syncs.phone.getAllWals();
      if (done(wals)) return wals;
      await world.settle();
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }
    return world.wal.syncs.phone.getAllWals();
  }

  int totalSeconds(List<Wal> wals) => wals.fold<int>(0, (total, wal) => total + wal.seconds);

  /// The controller asks for recovery through its session owner; the replay world has none, so wake
  /// the world's coordinator the way that request would.
  Future<void> recoveryPass() async {
    await world.coordinator.wake(WakeTrigger.dataStalled);
    await settleFiles();
  }

  /// Records [seconds] of phone-mic audio with the socket connected the whole time, then stops.
  Future<void> recordOnline(int seconds) async {
    await world.startLiveCapture();
    final session = world.hostApi.lastStartSessionId!;
    world.emitNativeState(PhoneMicCaptureState.running);
    for (var s = 0; s < seconds; s++) {
      world.injectAudioFrames(100, sessionId: session, firstFrameIndex: s * 100);
      await world.elapse(const Duration(seconds: 1));
    }
    expect(world.socket!.sentBinary, hasLength(seconds * 100), reason: 'every frame reached the server');
    await world.stopLiveCapture();
    await settleFiles();
  }

  ServerConversation conversation(String id, DateTime startedAt, List<(double, double)> spans) => ServerConversation(
        id: id,
        createdAt: startedAt,
        startedAt: startedAt,
        structured: Structured('fixture', 'fixture'),
        transcriptSegments: [
          for (final (i, span) in spans.indexed)
            TranscriptSegment(
              id: '$id-s$i',
              text: 'words',
              speaker: 'SPEAKER_00',
              isUser: true,
              personId: null,
              start: span.$1,
              end: span.$2,
              translations: [],
            ),
        ],
      );

  Future<void> serverCloses(ServerConversation memory) async {
    world.controller.onMessageEventReceived(ConversationProcessingStartedEvent(memory: memory));
    await settleFiles();
    world.controller.onMessageEventReceived(ConversationEvent(memory: memory, messages: []));
    await settleFiles();
  }

  test('phone mic: a recording the server never transcribed stays on the phone and is uploaded', () async {
    await recordOnline(130);

    final kept = await walsReach((wals) => totalSeconds(wals) >= 120);
    expect(totalSeconds(kept), greaterThanOrEqualTo(120), reason: 'sent audio is kept until a transcript confirms it');
    await recoveryPass();
    expect(world.uploads.attempts, isNotEmpty, reason: 'the recovery pass sends the audio for repair');
    await walsReach((wals) => wals.every((wal) => wal.status != WalStatus.miss));
    expect((await world.walCounts())[WalStatus.miss] ?? 0, 0, reason: 'nothing is left waiting after the upload');
  });

  test('phone mic: a conversation with no saved text uploads the recording for repair', () async {
    final origin = world.clock.now();
    await recordOnline(130);

    await serverCloses(conversation('c1', origin, const []));
    final stamped = await walsReach((wals) => wals.isNotEmpty && wals.every((wal) => wal.conversationId == 'c1'));
    expect(stamped.map((wal) => wal.conversationId).toSet(), {'c1'},
        reason: 'the copy is stamped with its conversation');
    await recoveryPass();

    expect(world.uploads.attempts, isNotEmpty);
    expect(world.uploads.attempts.map((attempt) => attempt.conversationId).toSet(), {'c1'});
  });

  test('phone mic: a transcript that covers the recording releases the copy without uploading', () async {
    final origin = world.clock.now();
    await recordOnline(130);

    await serverCloses(conversation('c1', origin, [for (var t = 1.0; t < 125; t += 20) (t, t + 15)]));
    expect(await walsReach((wals) => wals.isEmpty), isEmpty);

    await recoveryPass();
    expect(world.uploads.attempts, isEmpty, reason: 'transcribed audio is not uploaded again');
  });
}
