import 'dart:io';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/mobile_batch_buffer.dart';
import 'package:omi/services/wals/mobile_batch_upload_hold.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_batch.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';

import '../../support/custody_test_helpers.dart';

final _start = DateTime.utc(2026, 11, 25);

Wal _wal(int id, int seconds, {String session = 'recording'}) {
  final start = _start.millisecondsSinceEpoch ~/ 1000 + id;
  return Wal(
    timerStart: start,
    seconds: seconds,
    totalFrames: seconds * BleAudioCodec.opus.getFramesPerSecond(),
    codec: BleAudioCodec.opus,
    device: 'omimobilebatch$id',
    filePath: 'audio_omimobilebatch${id}_opus_16000_1_fs160_$start.bin',
    recordingSessionId: session,
    status: WalStatus.miss,
    storage: WalStorage.disk,
  );
}

void _publish(MobileBatchUploadHold hold, Wal wal) {
  hold.sealed(wal);
  expect(hold.published(wal), isTrue);
}

void main() {
  for (final (foreground, preview, limit, label) in [
    (false, false, 300, 'bg300'),
    (true, true, 300, 'fg_preview300'),
    (true, false, 60, 'fg60'),
  ]) {
    test('$label releases at $limit seconds of sealed session audio', () {
      fakeAsync((time) {
        var wakes = 0;
        final hold = MobileBatchUploadHold(
          enabled: () => true,
          wake: () => wakes++,
          now: () => _start.add(time.elapsed),
          foreground: foreground,
        )..setPreview(preview);
        final files = [for (var i = 0; i < limit ~/ 30; i++) _wal(i, i == 0 ? 29 : 30)];
        for (final file in files) {
          _publish(hold, file);
        }
        expect(wakes, 0);
        expect(files.every(hold.isHeld), isTrue);
        final otherSession = _wal(100, 1, session: 'other');
        _publish(hold, otherSession);
        expect(wakes, 0);

        _publish(hold, _wal(99, 1));
        expect(wakes, 1);
        expect(files.any(hold.isHeld), isFalse);
        expect(files.map(hold.label).toSet(), {label});
        expect(hold.isHeld(otherSession), isTrue);
        hold.clear();
      });
    });
  }

  test('foreground transition releases even a file whose index write is in flight', () {
    fakeAsync((time) {
      var wakes = 0;
      final hold = MobileBatchUploadHold(
        enabled: () => true,
        wake: () => wakes++,
        now: () => _start.add(time.elapsed),
        foreground: false,
      );
      final older = _wal(1, 8);
      final publishing = _wal(2, 3);
      _publish(hold, older);
      hold.sealed(publishing);
      hold.setForeground(true);
      expect(wakes, 1);
      expect(hold.isHeld(older), isFalse);
      expect(hold.label(older), 'bg300');
      expect(hold.published(publishing), isTrue);
      expect(wakes, 2);
      expect(hold.label(publishing), 'bg300');

      final newFile = _wal(3, 2);
      _publish(hold, newFile);
      expect(hold.isHeld(newFile), isTrue);
      hold.clear();
    });
  });

  test('capture end releases only that recording and still holds new audio', () {
    fakeAsync((time) {
      var wakes = 0;
      final hold = MobileBatchUploadHold(enabled: () => true, wake: () => wakes++, now: () => _start.add(time.elapsed));
      final ending = _wal(1, 7);
      final unrelated = _wal(2, 7, session: 'other');
      _publish(hold, ending);
      _publish(hold, unrelated);
      hold.captureEnded('recording');
      expect(wakes, 1);
      expect(hold.isHeld(ending), isFalse);
      expect(hold.isHeld(unrelated), isTrue);
      final reopened = _wal(3, 7);
      _publish(hold, reopened);
      expect(hold.isHeld(reopened), isTrue);
      hold.clear();
    });
  });

  test('an idle session wakes at the oldest seal deadline', () {
    fakeAsync((time) {
      var wakes = 0;
      final hold = MobileBatchUploadHold(enabled: () => true, wake: () => wakes++, now: () => _start.add(time.elapsed));
      final first = _wal(1, 12);
      final second = _wal(2, 8);
      _publish(hold, first);
      time.elapse(const Duration(seconds: 30));
      _publish(hold, second);
      time.elapse(const Duration(seconds: 29));
      expect(wakes, 0);
      time.elapse(const Duration(seconds: 1));
      expect(wakes, 1);
      expect([first, second].any(hold.isHeld), isFalse);
    });
  });

  test('preview becoming unavailable re-evaluates the oldest seal against 60 seconds', () {
    fakeAsync((time) {
      var wakes = 0;
      final hold = MobileBatchUploadHold(enabled: () => true, wake: () => wakes++, now: () => _start.add(time.elapsed))
        ..setPreview(true);
      final file = _wal(1, 29);
      _publish(hold, file);
      time.elapse(const Duration(seconds: 65));
      expect(wakes, 0);
      hold.setPreview(false);
      expect(wakes, 1);
      expect(hold.label(file), 'fg60');
    });
  });

  test('disabled holds use the immediate seal wake and the next tick releases queued files', () {
    fakeAsync((time) {
      var enabled = false;
      var wakes = 0;
      final hold = MobileBatchUploadHold(
        enabled: () => enabled,
        wake: () => wakes++,
        now: () => _start.add(time.elapsed),
      );
      final immediate = _wal(1, 7);
      hold.sealed(immediate);
      expect(hold.published(immediate), isFalse, reason: 'the existing publish path wakes immediately');
      expect(hold.isHeld(immediate), isFalse);
      expect(hold.label(immediate), 'none');
      enabled = true;
      final held = _wal(2, 7);
      _publish(hold, held);
      enabled = false;
      time.elapse(const Duration(seconds: 15));
      expect(wakes, 1);
      expect(hold.isHeld(held), isFalse);
      expect(hold.label(held), 'none');
    });
  });

  for (final (seconds, count, firstBatchSize) in [(55, 6, 5), (14, 22, 20)]) {
    test('one hold release drains every file with $firstBatchSize files in the first bounded request', () {
      fakeAsync((time) {
        final hold = MobileBatchUploadHold(
          enabled: () => true,
          wake: () {},
          now: () => _start.add(time.elapsed),
          foreground: false,
        );
        final files = [for (var i = 0; i < count; i++) _wal(i, seconds)];
        for (final file in files) {
          _publish(hold, file);
        }
        final pending = files.where((file) => !hold.isHeld(file)).toList();
        expect(pending, hasLength(count));
        final now = _start.millisecondsSinceEpoch ~/ 1000 + count;
        final first = nextSyncUploadBatch(pending, now, holdLabel: hold.label);
        expect(first, hasLength(firstBatchSize));
        expect(first.fold(0, (sum, wal) => sum + wal.seconds), lessThanOrEqualTo(300));
        expect(first, hasLength(lessThanOrEqualTo(20)));
        pending.removeWhere(first.contains);
        expect(nextSyncUploadBatch(pending, now, holdLabel: hold.label), hasLength(count - firstBatchSize));
      });
    });
  }

  test('restart re-scans sealed files whose journal had not yet been retired', () async {
    final directory = await Directory.systemTemp.createTemp('batch_hold_restart_');
    addTearDown(() => directory.delete(recursive: true));
    final before = MobileBatchUploadHold(enabled: () => true, wake: () {}, now: () => _start);
    addTearDown(before.clear);
    final journal = MobileBatchBuffer(
      directory: directory,
      onSealed: before.sealed,
      publish: (wal) async {
        expect(before.isHeld(wal), isTrue);
        throw StateError('interrupted before index commit');
      },
    );
    final frames = [
      [1, 2, 3],
      [4, 5, 6],
    ];
    for (var i = 0; i < frames.length; i++) {
      expect(
        journal.append(frames[i],
            uid: 'owner', codec: BleAudioCodec.opus, now: _start.add(Duration(seconds: i)), recordingSessionId: 'a'),
        isTrue,
      );
      journal.seal();
    }
    await journal.pending;
    final recovered = await MobileBatchBuffer.recover(directory, []);
    recovered.sort((a, b) => a.timerStart.compareTo(b.timerStart));
    expect(recovered, hasLength(2));
    final after = MobileBatchUploadHold(enabled: () => true, wake: () {}, now: () => _start);
    for (var i = 0; i < recovered.length; i++) {
      final wal = recovered[i];
      expect(wal.totalFrames, 1);
      expect(wal.ownerUid, 'owner');
      expect(wal.status, WalStatus.miss);
      expect(after.isHeld(wal), isFalse);
      expect(await File('${directory.path}/${wal.filePath}').readAsBytes(), [3, 0, 0, 0, ...frames[i]]);
    }
    expect(await MobileBatchBuffer.recover(directory, recovered), hasLength(2));
  });

  test('a new drain uploads held files from the durable WAL index after restart', () async {
    final directory = await custodyDirectory();
    addTearDown(() => directory.delete(recursive: true));
    final requests = <List<String>>[];
    final claims = <bool>[];
    final gate = SyncUploadGate(
      limiter: SyncRateLimiter.instance,
      fairUseStatusLoader: () async => {'stage': 'none'},
      uploader: (files,
          {onUploadProgress,
          conversationId,
          captureEvidence,
          recordingSessionId,
          audioStartSeconds,
          audioEndSeconds,
          claimLiveCapture = false,
          geolocation}) async {
        requests.add(files.map((file) => file.uri.pathSegments.last).toList());
        claims.add(claimLiveCapture);
        return UploadFilesResult.queued('synthetic-job');
      },
    );
    final before = MobileBatchUploadHold(enabled: () => true, wake: () {}, now: () => _start);
    addTearDown(before.clear);
    final ledger = await custodyLedger(gate: gate, now: () => _start)
      ..mobileBatchUploadHold = before;
    final buffer = MobileBatchBuffer(
      directory: directory,
      onSealed: before.sealed,
      publish: (wal) async {
        wal.conversationId = 'shared-conversation';
        await ledger.addExternalWal(wal, admittedGeneration: ledger.sessionGeneration);
        expect(await ledger.hasDurableWal(wal, admittedGeneration: ledger.sessionGeneration), isTrue);
        expect(before.published(wal), isTrue);
      },
    );
    expect(buffer.append([1], uid: 'owner', codec: BleAudioCodec.opus, now: _start, recordingSessionId: 'r'), isTrue);
    buffer.seal();
    expect(
        buffer.append([2], uid: 'owner', codec: BleAudioCodec.opus, now: _start, recordingSessionId: 'ready'), isTrue);
    await buffer.close();
    before.captureEnded('ready');
    await ledger.syncAll();
    final wals = await ledger.getAllWals();
    final ready = wals.singleWhere((wal) => wal.recordingSessionId == 'ready');
    final file = wals.singleWhere((wal) => wal.recordingSessionId == 'r');
    expect(requests, [
      [ready.filePath]
    ]);
    expect(claims, [false], reason: 'a held sibling must still prevent an immutable partial capture claim');
    expect(file.status, WalStatus.miss);
    expect(await File('${directory.path}/${file.filePath}.batch-journal').exists(), isFalse);

    final restarted = await custodyLedger(gate: gate, now: () => _start);
    await restarted.syncAll();
    expect(requests, [
      [ready.filePath],
      [file.filePath],
    ]);
    expect((await restarted.getAllWals()).every((wal) => wal.status == WalStatus.uploaded), isTrue);
    expect(await File('${directory.path}/${file.filePath}').readAsBytes(), [1, 0, 0, 0, 1]);
  });
}
