// The Home model (SCA-5226): every row kind, the order, the live row's place, and the deadlines.
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/conversations/home/home_model.dart';
import 'package:omi/pages/conversations/home/home_prompt_slot.dart';

final now = DateTime(2026, 11, 27, 14, 0);
final today = DateTime(2026, 11, 27);
final yesterday = DateTime(2026, 11, 26);

ServerConversation convo(String id, DateTime at,
        {ConversationTileState? tile,
        bool locked = false,
        bool homeHidden = false,
        bool recording = false,
        String? homeStep,
        ConversationStatus status = ConversationStatus.completed}) =>
    ServerConversation(
      id: id,
      createdAt: at,
      startedAt: at,
      finishedAt: at.add(const Duration(minutes: 5)),
      structured: Structured('Title $id', '', emoji: '☕'),
      isLocked: locked,
      status: status,
      homeStep: homeStep,
      v3: tile == null && !homeHidden && !recording
          ? null
          : ConversationV3Fields(tileState: tile, homeHidden: homeHidden, recording: recording),
    );

LocalRecording saved(String id, DateTime at,
        {LocalRecordingState state = LocalRecordingState.pending, DateTime? uploadedAt}) =>
    LocalRecording(
      fileName: id,
      filePath: '/tmp/$id',
      timerStart: at.millisecondsSinceEpoch ~/ 1000,
      codec: BleAudioCodec.opus,
      frameSize: 160,
      sizeBytes: 100,
      seconds: 2,
      state: state,
      uploadedAt: uploadedAt,
    );

List<String> keys(HomeModel model) => [for (final r in model.rows) r.key];

void main() {
  test('days are newest first and rows within a day newest first, across kinds', () {
    final model = buildHome(HomeInputs(
      now: now,
      listed: [
        convo('a', today.add(const Duration(hours: 9))),
        convo('b', yesterday.add(const Duration(hours: 20))),
        convo('c', today.add(const Duration(hours: 12))),
      ],
      saved: [saved('r', today.add(const Duration(hours: 10)), state: LocalRecordingState.processing)],
    ));
    expect(model.days.map((d) => d.date), [today, yesterday]);
    expect(keys(model), ['c', 'saved_r', 'a', 'b']);
  });

  test('the live row leads Today, followed by Finishing…, and the live conversation is not listed twice', () {
    final live = convo('live', yesterday.add(const Duration(hours: 23, minutes: 50)), tile: ConversationTileState.live);
    final model = buildHome(HomeInputs(
      now: now,
      listed: [live, convo('a', today.add(const Duration(hours: 13)))],
      live: live,
      finishing: convo('0', now),
    ));
    expect(model.days.first.date, today);
    expect(keys(model), ['live', 'finishing', 'a']);
    expect((model.rows.first as HomeLiveRow).kind, HomeLiveKind.conversation);
  });

  test('live row precedence: server conversation, then call, then Transcribe Later, then a streaming capture', () {
    HomeLiveKind? kind({ServerConversation? live, bool call = false, bool later = false, bool streaming = false}) =>
        homeLiveKind(
            live: live, streaming: streaming, callActive: call, transcribeLater: later, listeningSuppressed: false);
    final live = convo('live', now, tile: ConversationTileState.live);
    expect(kind(live: live, call: true, later: true, streaming: true), HomeLiveKind.conversation);
    expect(kind(call: true, later: true, streaming: true), HomeLiveKind.call);
    expect(kind(later: true, streaming: true), HomeLiveKind.transcribeLater);
    expect(kind(streaming: true), HomeLiveKind.capture);
    expect(kind(), isNull);
    // A failed or hidden live conversation does not stand for the capture.
    expect(kind(live: convo('x', now, tile: ConversationTileState.failed), streaming: true), HomeLiveKind.capture);
  });

  test('End hides the capture row until speech brings it back', () {
    final model = buildHome(HomeInputs(now: now, listed: const [], streaming: true, listeningSuppressed: true));
    expect(model.isEmpty, isTrue);
  });

  test('a live row with nothing else listed still opens Today', () {
    final model = buildHome(HomeInputs(now: now, listed: const [], streaming: true));
    expect(model.days.single.date, today);
    expect(keys(model), ['live']);
  });

  test('failed conversations are in Activity, not Home; neither are hidden or recording documents', () {
    final model = buildHome(HomeInputs(now: now, listed: [
      convo('failed', today, tile: ConversationTileState.failed),
      convo('legacy-failed', today, status: ConversationStatus.failed),
      convo('hidden', today, homeHidden: true),
      convo('rec', today, recording: true),
      convo('done', today),
    ]));
    expect(keys(model), ['done']);
  });

  test('a recording on this phone is on Home only while it is sent or processed', () {
    final at = today.add(const Duration(hours: 9));
    final model = buildHome(HomeInputs(now: now, listed: const [], saved: [
      saved('waiting', at),
      saved('failed', at, state: LocalRecordingState.failed),
      saved('sending', at, state: LocalRecordingState.uploading),
      saved('processing', at, state: LocalRecordingState.processing),
    ]));
    expect(keys(model), unorderedEquals(['saved_sending', 'saved_processing']));
  });

  test('rows pending delete are hidden', () {
    final model =
        buildHome(HomeInputs(now: now, listed: [convo('a', today), convo('b', today)], hiddenIds: const {'a'}));
    expect(keys(model), ['b']);
  });

  test('locked conversations and held audio on one day become one row, placed by its newest member', () {
    final model = buildHome(HomeInputs(
      now: now,
      listed: [
        convo('l1', today.add(const Duration(hours: 8)), locked: true),
        convo('a', today.add(const Duration(hours: 9))),
        convo('l2', today.add(const Duration(hours: 11)), locked: true),
      ],
      held: [
        HeldAudioRecording(
            id: 'h', startedAt: today.add(const Duration(hours: 7)).millisecondsSinceEpoch ~/ 1000, seconds: 60),
      ],
      heldMore: 2,
    ));
    expect(keys(model), ['locked_${today.toIso8601String()}', 'a']);
    final locked = model.rows.first as HomeLockedRow;
    expect(locked.count, 5);
  });

  test('held recordings the server counted but did not list still get a locked row', () {
    final onLockedDay = buildHome(HomeInputs(
      now: now,
      listed: [convo('l', yesterday, locked: true)],
      heldMore: 3,
    ));
    expect((onLockedDay.rows.single as HomeLockedRow).count, 4);
    final alone = buildHome(HomeInputs(now: now, listed: [convo('a', yesterday)], heldMore: 2));
    expect(alone.days.first.date, today);
    expect((alone.rows.first as HomeLockedRow).count, 2);
  });

  test('a failed live conversation, v3- or legacy-shaped, does not stand for the live row and is not listed', () {
    final at = today.add(const Duration(hours: 9));
    for (final failed in [
      convo('lf', at, status: ConversationStatus.failed),
      convo('vf', at, tile: ConversationTileState.failed),
    ]) {
      final model = buildHome(HomeInputs(
        now: now,
        listed: [failed, convo('later', today.add(const Duration(hours: 13)))],
        live: failed,
        streaming: true,
      ));
      expect(keys(model), ['live', 'later']);
      expect((model.rows.first as HomeLiveRow).kind, HomeLiveKind.capture);
    }
    final deleted =
        ServerConversation(id: 'del', createdAt: at, startedAt: at, structured: Structured('', ''), deleted: true);
    expect(keys(buildHome(HomeInputs(now: now, listed: const [], live: deleted))), isEmpty);
  });

  test('a filtered view lists only conversations, locked ones in place', () {
    final model = buildHome(HomeInputs(
      now: now,
      defaultView: false,
      listed: [convo('l', today, locked: true)],
      streaming: true,
      saved: [saved('r', today)],
      finishing: convo('0', now),
    ));
    expect(keys(model), ['l']);
  });

  test('duplicates keep their first occurrence', () {
    final model = buildHome(HomeInputs(now: now, listed: [convo('a', today), convo('a', yesterday)]));
    expect(model.days.single.date, today);
  });

  group('deadlines', () {
    test('a conversation step is overdue only past the deadline, measured from when it finished', () {
      final finished = now.subtract(HomeDeadlines.conversationStep);
      final writing = convo('w', finished.subtract(const Duration(minutes: 5)), tile: ConversationTileState.writing);
      expect(conversationStepOverdue(writing, now), isFalse);
      expect(conversationStepOverdue(writing, now.add(const Duration(seconds: 1))), isTrue);
      final done = convo('d', finished.subtract(const Duration(hours: 5)), tile: ConversationTileState.done);
      expect(conversationStepOverdue(done, now), isFalse);
    });

    test('a legacy-shaped row falls back to its Home step', () {
      final row = convo('t', now.subtract(const Duration(hours: 1)),
          homeStep: 'transcribing', status: ConversationStatus.processing);
      expect(homeTileState(row), ConversationTileState.transcribing);
      expect(conversationStepOverdue(row, now), isTrue);
    });

    test('a saved recording is overdue only while processing past its deadline', () {
      final uploaded = now.subtract(HomeDeadlines.savedProcessing + const Duration(minutes: 1));
      expect(
          savedProcessingOverdue(saved('p', today, state: LocalRecordingState.processing, uploadedAt: uploaded), now),
          isTrue);
      expect(savedProcessingOverdue(saved('p', today, state: LocalRecordingState.processing, uploadedAt: now), now),
          isFalse);
      expect(savedProcessingOverdue(saved('q', today, uploadedAt: uploaded), now), isFalse);
    });
  });

  test('one prompt at most: payment, then firmware, then voice profile, then Review', () {
    HomePrompt? prompt({bool p = false, bool f = false, bool v = false, bool r = false}) =>
        homePrompt(paymentIssue: p, firmwareUpdate: f, voiceProfileMissing: v, reviewWaiting: r);
    expect(prompt(p: true, f: true, v: true, r: true), HomePrompt.payment);
    expect(prompt(f: true, v: true, r: true), HomePrompt.firmware);
    expect(prompt(v: true, r: true), HomePrompt.voiceProfile);
    expect(prompt(r: true), HomePrompt.review);
    expect(prompt(), isNull);
  });
}
