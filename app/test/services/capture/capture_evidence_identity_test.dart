import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/phone_mic_pigeon.g.dart';
import 'package:omi/services/wals/sync_upload_batch.dart';
import 'package:omi/services/wals/wal.dart';

import '../../support/capture/capture_replay_world.dart';
import '../../support/capture/scripted_device_connection.dart';

const _darkWrite = bool.fromEnvironment('CAPTURE_EVIDENCE_V1_DARK_WRITE');

void main() {
  late Directory tempDir;
  late CaptureReplayWorld world;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('capture_evidence_');
    world = await CaptureReplayWorld.boot(tempDir: tempDir);
  });

  tearDown(() async {
    await world.dispose();
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  List<Map<String, dynamic>> evidenceRecords() {
    final out = <Map<String, dynamic>>[];
    for (final entry in world.sockets) {
      for (final text in entry.transport.sentText) {
        final decoded = jsonDecode(text);
        if (decoded is Map<String, dynamic> && decoded['type'] == 'capture_evidence_frame') {
          out.add(decoded);
        }
      }
    }
    return out;
  }

  String tuple(Map<String, dynamic> record) =>
      '${record['capture_root']}/${record['clock_epoch']}/${record['source_frame']}';

  Set<String> tuples(Iterable<Map<String, dynamic>> records) => records.map(tuple).toSet();

  String singleRoot(List<Map<String, dynamic>> records) {
    final roots = records.map((r) => r['capture_root']).toSet();
    expect(roots, hasLength(1));
    return roots.single as String;
  }

  Future<List<List<int>>> captureSeconds(int seconds, {required int frameCursor}) async {
    final sessionId = world.hostApi.lastStartSessionId!;
    final frames = <List<int>>[];
    for (var s = 0; s < seconds; s++) {
      frames.addAll(world.injectAudioFrames(100, sessionId: sessionId, firstFrameIndex: frameCursor + s * 100));
      await world.elapse(const Duration(seconds: 1));
    }
    return frames;
  }

  Future<void> startRunning() async {
    await world.startLiveCapture();
    world.emitNativeState(PhoneMicCaptureState.running);
  }

  group('dark-write enabled', skip: _darkWrite ? null : 'requires CAPTURE_EVIDENCE_V1_DARK_WRITE=true', () {
    test('one capture session keeps one root with strictly increasing ordinals', () async {
      await startRunning();
      await captureSeconds(2, frameCursor: 0);

      final records = evidenceRecords();
      expect(records, hasLength(200));
      singleRoot(records);
      expect([for (final r in records) r['source_frame']], List.generate(200, (i) => i));
      expect(records.map((r) => r['clock_epoch']).toSet(), {0});
    });

    test('direct phone WAL reset mid-capture rotates the evidence root', () async {
      await startRunning();
      await captureSeconds(1, frameCursor: 0);
      final before = evidenceRecords();
      expect(before, hasLength(100));
      final rootBefore = singleRoot(before);

      world.wal.syncs.phone.clearUserData();
      await captureSeconds(1, frameCursor: 10000);

      final all = evidenceRecords();
      final after = all.sublist(before.length);
      expect(after, hasLength(100));
      final rootAfter = singleRoot(after);
      expect(rootAfter, isNot(rootBefore));
      expect(tuples(after).intersection(tuples(before)), isEmpty);
      expect(all.sublist(0, before.length).every((r) => r['capture_root'] == rootBefore), isTrue);
    });

    test('controller clearUserData alone rotates the evidence root', () async {
      await startRunning();
      await captureSeconds(1, frameCursor: 0);
      final before = evidenceRecords();
      final rootBefore = singleRoot(before);

      world.controller.clearUserData();
      await captureSeconds(1, frameCursor: 10000);

      final after = evidenceRecords().sublist(before.length);
      expect(after, hasLength(100));
      expect(singleRoot(after), isNot(rootBefore));
      expect(tuples(after).intersection(tuples(before)), isEmpty);
    });

    test('logout order and bare uid changes rotate the evidence root', () async {
      SharedPreferencesUtil().uid = 'account-a';
      await startRunning();
      await captureSeconds(1, frameCursor: 0);
      final rootA = singleRoot(evidenceRecords());
      var cursor = evidenceRecords().length;

      world.wal.syncs.phone.clearUserData();
      world.injectAudioFrames(1, sessionId: world.hostApi.lastStartSessionId!, firstFrameIndex: 10000);
      SharedPreferencesUtil().uid = 'account-b';
      await captureSeconds(1, frameCursor: 20000);

      final afterSwitch = evidenceRecords().sublist(cursor);
      expect(afterSwitch, hasLength(101));
      final rootReset = afterSwitch.first['capture_root'] as String;
      expect(rootReset, isNot(rootA));
      final rootB = singleRoot(afterSwitch.sublist(1));
      expect(rootB, isNot(rootA));
      expect(rootB, isNot(rootReset));
      cursor += afterSwitch.length;

      SharedPreferencesUtil().uid = 'account-c';
      await captureSeconds(1, frameCursor: 30000);
      final afterUid = evidenceRecords().sublist(cursor);
      expect(afterUid, hasLength(100));
      final rootC = singleRoot(afterUid);
      expect(rootC, isNot(rootB));
      expect(rootC, isNot(rootA));
    });

    test('codec change on the same allocator rotates the root and restarts the ordinal', () async {
      await startRunning();
      await captureSeconds(1, frameCursor: 0);
      final before = evidenceRecords();
      final rootBefore = singleRoot(before);

      await world.wal.syncs.phone.onAudioCodecChanged(BleAudioCodec.pcm16);
      await captureSeconds(1, frameCursor: 10000);

      final after = evidenceRecords().sublist(before.length);
      expect(after, hasLength(100));
      expect(singleRoot(after), isNot(rootBefore));
      expect(after.first['source_frame'], 0);
      expect(tuples(after).intersection(tuples(before)), isEmpty);
    });

    test('deleting WALs never reissues a tuple inside one process', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      await startRunning();
      await captureSeconds(1, frameCursor: 0);
      final onlineRecords = evidenceRecords();
      final root = singleRoot(onlineRecords);
      final consumed = tuples(onlineRecords);

      await world.wal.syncs.phone.finalizeCurrentSession();
      await captureSeconds(1, frameCursor: 10000);
      consumed.addAll(tuples(evidenceRecords().sublist(onlineRecords.length)));

      world.setConnected(false);
      world.socket!.emitClose();
      await world.settle();
      await captureSeconds(1, frameCursor: 20000);
      await world.wal.syncs.phone.finalizeCurrentSession();
      await captureSeconds(1, frameCursor: 30000);
      await world.wal.syncs.phone.finalizeCurrentSession();

      final wals = await world.wal.syncs.phone.getAllWals();
      final pending = wals.where((w) => w.status == WalStatus.miss).toList();
      expect(pending.length, greaterThanOrEqualTo(2));
      for (final wal in wals) {
        if (wal.captureRoot != null && wal.sourceFrameStart != null) {
          consumed.addAll(
            List.generate(
              wal.totalFrames,
              (i) => '${wal.captureRoot}/${wal.sourceClockEpoch}/${wal.sourceFrameStart! + i}',
            ),
          );
        }
      }
      await world.wal.syncs.phone.deleteWal(pending.first);
      wals.last.markCorrupted();
      await world.wal.syncs.phone.deleteAllCorruptedWals();
      await world.wal.syncs.phone.deleteAllPendingWals();
      await world.wal.syncs.phone.deleteAllSyncedWals();
      expect(await world.wal.syncs.phone.getAllWals(), isEmpty);

      await captureSeconds(1, frameCursor: 40000);
      final newFrames = world.wal.syncs.phone.testFrames;
      expect(newFrames, hasLength(100));
      expect(newFrames.map((f) => f.captureRoot).toSet(), {root});
      expect(
        newFrames
            .map((f) => '${f.captureRoot}/${f.sourceClockEpoch}/${f.sourceFramePosition}')
            .toSet()
            .intersection(consumed),
        isEmpty,
      );
    });

    test('fresh install with no surviving WALs allocates a new root', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      await startRunning();
      await captureSeconds(1, frameCursor: 0);
      final rootBefore = singleRoot(evidenceRecords());
      await world.dispose();

      final freshDir = Directory('${tempDir.path}/fresh')..createSync();
      SharedPreferences.setMockInitialValues({});
      world = await CaptureReplayWorld.boot(tempDir: freshDir);
      expect(await world.wal.syncs.phone.getAllWals(), isEmpty);

      await startRunning();
      await captureSeconds(1, frameCursor: 10000);
      final records = evidenceRecords();
      final after = records.sublist(records.length - 100);
      expect(singleRoot(after), isNot(rootBefore));
    });

    test('restart keeps stored WAL claim roots but opens a new live namespace', () async {
      await startRunning();
      await captureSeconds(1, frameCursor: 0);
      final rootBefore = singleRoot(evidenceRecords());
      world.setConnected(false);
      world.socket!.emitClose();
      await world.settle();
      await captureSeconds(1, frameCursor: 10000);
      await world.wal.syncs.phone.finalizeCurrentSession();
      final stored = (await world.wal.syncs.phone.getAllWals()).single;
      expect(stored.captureRoot, rootBefore);
      final storedClaim = '${stored.captureRoot}/${stored.sourceClockEpoch}/${stored.sourceFrameStart}';

      world.killProcess();
      world.connected = true;
      await world.reconstructProcess();

      final reloaded = (await world.wal.syncs.phone.getAllWals()).single;
      expect(reloaded.captureRoot, rootBefore);
      final walPath = await Wal.getFilePath(reloaded.filePath);
      final header = jsonDecode(captureEvidenceUploadHeader([reloaded], [File(walPath!)])!);
      expect(
        '${header['files'].single['capture_root']}/${header['files'].single['clock_epoch']}/${header['files'].single['source_frame_start']}',
        storedClaim,
      );

      await startRunning();
      await captureSeconds(1, frameCursor: 20000);
      final records = evidenceRecords();
      final live = records.sublist(records.length - 100);
      final liveRoot = singleRoot(live);
      expect(liveRoot, isNot(rootBefore));
      expect(live.first['source_frame'], 0);
    });

    test('WAL serialization and the upload boundary carry the live root', () async {
      await startRunning();
      await captureSeconds(1, frameCursor: 0);
      final root = singleRoot(evidenceRecords());
      world.setConnected(false);
      world.socket!.emitClose();
      await world.settle();
      await captureSeconds(1, frameCursor: 10000);
      await world.wal.syncs.phone.finalizeCurrentSession();

      final wal = (await world.wal.syncs.phone.getAllWals()).single;
      expect(wal.captureRoot, root);
      final roundTripped = Wal.fromJson(wal.toJson());
      expect(roundTripped.captureRoot, root);
      expect(roundTripped.sourceFrameStart, wal.sourceFrameStart);
      expect(roundTripped.sourceClockEpoch, wal.sourceClockEpoch);

      world.setConnected(true);
      await world.wal.syncs.phone.syncAll();
      final claim = world.uploads.attempts.last.captureEvidence;
      expect(claim, isNotNull);
      final parsed = jsonDecode(claim!);
      expect(parsed['version'], 1);
      expect((parsed['files'] as List).map((f) => f['capture_root']).toSet(), {root});
    });

    test('a mid-buffer root rotation stores and uploads one claim per run', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      SharedPreferencesUtil().uid = 'account-a';
      await startRunning();
      await captureSeconds(1, frameCursor: 0);
      final first = evidenceRecords();
      final rootA = singleRoot(first);

      SharedPreferencesUtil().uid = 'account-b';
      await captureSeconds(1, frameCursor: 10000);
      final rootB = singleRoot(evidenceRecords().sublist(first.length));
      expect(rootB, isNot(rootA));

      world.setConnected(false);
      world.socket!.emitClose();
      await world.settle();
      await captureSeconds(1, frameCursor: 20000);

      await world.wal.syncs.phone.finalizeCurrentSession();

      final wals = await world.wal.syncs.phone.getAllWals();
      final byRoot = {for (final wal in wals) wal.captureRoot: wal};
      expect(byRoot.keys.toSet(), {rootA, rootB}, reason: 'each contiguous run keeps its own claim');
      expect((byRoot[rootA]!.sourceFrameStart, byRoot[rootA]!.totalFrames), (0, 100));
      expect((byRoot[rootB]!.sourceFrameStart, byRoot[rootB]!.totalFrames), (0, 200));
      expect(byRoot[rootA]!.channel, 1);
      expect(byRoot[rootA]!.sampleRate, greaterThan(0));

      world.setConnected(true);
      await world.wal.syncs.phone.syncAll();
      final claim = world.uploads.attempts.last.captureEvidence;
      expect(claim, isNotNull);
      final parsed = jsonDecode(claim!);
      expect((parsed['files'] as List).map((f) => f['capture_root']).toSet(), {rootB});
    });

    test('a pendant opus_fs320 stream claims with the normalized opus codec', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      await world.dispose();
      world = await CaptureReplayWorld.boot(tempDir: tempDir, pendantCodec: BleAudioCodec.opusFS320);
      final link = ScriptedDeviceConnection();
      world.deviceConnection = link;
      final pendant = BtDevice(id: 'pendant-1', name: 'Omi', type: DeviceType.omi, rssi: -40);
      await world.controller.streamDeviceRecording(device: pendant);
      await world.settle();

      for (var i = 0; i < 60; i++) {
        link.emitAudio();
      }
      await world.settle();
      world.setConnected(false);
      world.socket!.emitClose();
      await world.settle();
      await world.wal.syncs.phone.finalizeCurrentSession();

      final wals = await world.wal.syncs.phone.getAllWals();
      final rooted = wals.where((wal) => wal.captureRoot != null).toList();
      expect(rooted, isNotEmpty, reason: 'the pendant live stream carries rooted frames');
      final wal = rooted.single;
      expect(wal.codec, BleAudioCodec.opusFS320);
      expect(wal.channel, 1);
      expect(wal.totalFrames, greaterThan(0));

      world.setConnected(true);
      await world.wal.syncs.phone.syncAll();
      final claim = world.uploads.attempts.last.captureEvidence;
      expect(claim, isNotNull);
      final parsed = jsonDecode(claim!);
      final file = (parsed['files'] as List).single;
      expect(file['codec'], 'opus', reason: 'the wire token stays opus for every supported Opus variant');
      expect(file['frame_count'], wal.totalFrames);
      expect(file['capture_root'], wal.captureRoot);
    });

    test('a native interruption and recovery keeps one root with contiguous ordinals', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      await startRunning();
      await captureSeconds(1, frameCursor: 0);
      final root = singleRoot(evidenceRecords());
      final sessionId = world.hostApi.lastStartSessionId!;

      world.emitNativeState(PhoneMicCaptureState.interrupted, sessionId: sessionId);
      await world.settle();
      world.emitNativeState(PhoneMicCaptureState.running, sessionId: sessionId);
      await world.settle();
      await captureSeconds(1, frameCursor: 10000);

      final records = evidenceRecords();
      expect(records, hasLength(200));
      expect(singleRoot(records), root);
      expect([for (final r in records) r['source_frame']], List.generate(200, (i) => i));

      world.setConnected(false);
      world.socket!.emitClose();
      await world.settle();
      await captureSeconds(1, frameCursor: 20000);
      await world.wal.syncs.phone.finalizeCurrentSession();

      final rooted = (await world.wal.syncs.phone.getAllWals()).where((w) => w.captureRoot != null).toList();
      expect(rooted, isNotEmpty);
      expect(rooted.map((w) => w.captureRoot).toSet(), {root});
    });

    test('a padded phone-mic flush tail keeps the session root and frame count', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      await startRunning();
      final sessionId = world.hostApi.lastStartSessionId!;

      world.setConnected(false);
      world.socket!.emitClose();
      await world.settle();
      world.mic.onAudioFrame(Uint8List.fromList(List.filled(700, 0xAB)), sessionId);
      await world.settle();
      await world.stopLiveCapture();
      await world.wal.syncs.phone.finalizeCurrentSession();

      final rooted = (await world.wal.syncs.phone.getAllWals()).where((w) => w.captureRoot != null).toList();
      expect(rooted, isNotEmpty, reason: 'the padded tail lands in a rooted WAL');
      final wal = rooted.last;
      final root = wal.captureRoot;
      expect(wal.sourceFrameStart, 0);
      expect(wal.totalFrames, 3, reason: 'two full frames plus one zero-padded tail');
      final walPath = await Wal.getFilePath(wal.filePath);
      final bytes = await File(walPath!).readAsBytes();
      var offset = 0;
      var frames = 0;
      var lastLength = 0;
      while (offset + 4 <= bytes.length) {
        lastLength = ByteData.sublistView(bytes, offset).getUint32(0, Endian.little);
        offset += 4 + lastLength;
        frames++;
      }
      expect(frames, 3);
      expect(lastLength, 320);

      world.setConnected(true);
      await world.wal.syncs.phone.syncAll();
      final claim = world.uploads.attempts.last.captureEvidence;
      expect(claim, isNotNull);
      final parsed = jsonDecode(claim!);
      expect((parsed['files'] as List).map((f) => f['frame_count']).toSet(), {3});
      expect((parsed['files'] as List).map((f) => f['capture_root']).toSet(), {root});
    });

    test('a reconnect keeps the claim namespace and uploads the recovered WAL claims', () async {
      SharedPreferencesUtil().unlimitedLocalStorageEnabled = true;
      await startRunning();
      await captureSeconds(1, frameCursor: 0);
      final root = singleRoot(evidenceRecords());

      world.setConnected(false);
      world.socket!.emitClose();
      await world.settle();
      await captureSeconds(1, frameCursor: 10000);

      world.setConnected(true);
      await world.settle();
      await captureSeconds(1, frameCursor: 20000);
      await world.wal.syncs.phone.finalizeCurrentSession();

      final wals = await world.wal.syncs.phone.getAllWals();
      final rooted = wals.where((w) => w.captureRoot != null).toList();
      expect(rooted, isNotEmpty);
      expect(rooted.map((w) => w.captureRoot).toSet(), {root});

      await world.wal.syncs.phone.syncAll();
      final claimed = world.uploads.attempts.where((a) => a.captureEvidence != null).toList();
      expect(claimed, isNotEmpty);
      for (final attempt in claimed) {
        final parsed = jsonDecode(attempt.captureEvidence!);
        expect((parsed['files'] as List).map((f) => f['capture_root']).toSet(), {root});
      }
    });
  });

  group('dark-write disabled', skip: _darkWrite ? 'CAPTURE_EVIDENCE_V1_DARK_WRITE is on' : null, () {
    test('no evidence control records, binary audio unchanged, no WAL fields, no header', () async {
      await startRunning();
      final sent = await captureSeconds(1, frameCursor: 0);

      expect(world.socket!.sentBinary, hasLength(100));
      expect(world.socket!.sentBinary, sent);
      expect(evidenceRecords(), isEmpty);
      expect(world.socket!.sentText.where((t) => t.contains('capture_evidence')), isEmpty);

      world.setConnected(false);
      world.socket!.emitClose();
      await world.settle();
      await captureSeconds(1, frameCursor: 10000);
      await world.wal.syncs.phone.finalizeCurrentSession();
      final wal = (await world.wal.syncs.phone.getAllWals()).single;
      expect(wal.captureRoot, isNull);
      expect(wal.sourceFrameStart, isNull);
      expect(wal.sourceClockEpoch, isNull);
      expect(wal.toJson().containsKey('capture_root'), isFalse);

      final walPath = await Wal.getFilePath(wal.filePath);
      expect(captureEvidenceUploadHeader([wal], [File(walPath!)]), isNull);
    });
  });
}
