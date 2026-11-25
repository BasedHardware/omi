import 'dart:io';
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'pendant_ring_custody_test.dart' show v1Info;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory dir;
  setUp(() async {
    dir = await Directory.systemTemp.createTemp('custody_safety_');
    SharedPreferences.setMockInitialValues({'uid': 'owner'});
    await SharedPreferencesUtil.init();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (_) async => dir.path);
    await WalFileManager.init();
    await WalFileManager.saveWals([]);
  });
  tearDown(() async {
    await dir.delete(recursive: true);
  });
  Future<Wal> row({WalStatus status = WalStatus.miss}) async {
    await File('${dir.path}/proof.bin').writeAsBytes([1, 17], flush: true);
    return Wal(
        codec: BleAudioCodec.opus,
        timerStart: 1000,
        seconds: 1,
        totalFrames: 1,
        filePath: 'proof.bin',
        storage: WalStorage.disk,
        status: status,
        ownerUid: 'owner',
        device: 'device',
        liveRingId: 7,
        liveOrdinalStart: 0,
        liveOrdinalEnd: 1,
        liveDeviceId: 'device',
        fileSha256: sha256.convert([1, 17]).toString());
  }

  test('R16 empty legacy receipt never replays ADVANCE or suppresses a write', () async {
    final store = PendantCustodyStore(directoryProvider: () async => Directory('${dir.path}/custody'));
    await store.updateDownloadedRanges('device', 7, (ranges) {
      ranges.add(const RingRangeProof(startSeq: 100, endSeq: 101, wals: []));
    });
    final custody = PendantRingCustody(store: store);
    final replay = <int>[];
    await custody.beginConnection('device', 1, v1Info(readSeq: 100, writeSeq: 110), replayAdvance: (seq) async {
      replay.add(seq);
      return 0;
    });
    expect(replay, isEmpty);
    expect(await custody.validatedRecordRanges('device', 1, 7), isEmpty);
    await custody.flush();
  });
  test('R16 ownerless live proof is rejected even with indexed bytes', () async {
    await WalFileManager.saveWals([await row()]);
    expect(
        await walFileManagerCustodyValidator(CustodyWalRef(
            fileName: 'proof.bin',
            bytes: 2,
            frames: 1,
            liveDeviceId: 'device',
            liveRingId: 7,
            liveOrdinalStart: 0,
            liveOrdinalEnd: 1,
            fileSha256: sha256.convert([1, 17]).toString())),
        isFalse);
  });
  test('R16 corrupted indexed row never authorizes custody', () async {
    await WalFileManager.saveWals([await row(status: WalStatus.corrupted)]);
    expect(
        await walFileManagerCustodyValidator(CustodyWalRef(
            fileName: 'proof.bin',
            bytes: 2,
            frames: 1,
            ownerUid: 'owner',
            liveDeviceId: 'device',
            liveRingId: 7,
            liveOrdinalStart: 0,
            liveOrdinalEnd: 1,
            fileSha256: sha256.convert([1, 17]).toString())),
        isFalse);
  });
  test('R16 same length replacement never authorizes custody', () async {
    await WalFileManager.saveWals([await row()]);
    await File('${dir.path}/proof.bin').writeAsBytes([1, 18], flush: true);
    expect(
        await walFileManagerCustodyValidator(CustodyWalRef(
            fileName: 'proof.bin',
            bytes: 2,
            frames: 1,
            ownerUid: 'owner',
            liveDeviceId: 'device',
            liveRingId: 7,
            liveOrdinalStart: 0,
            liveOrdinalEnd: 1,
            fileSha256: sha256.convert([1, 17]).toString())),
        isFalse);
  });
  CustodyWalRef liveRef({String? owner = 'owner', String? device = 'device'}) => CustodyWalRef(
      fileName: 'proof.bin',
      bytes: 2,
      frames: 1,
      ownerUid: owner,
      liveDeviceId: device,
      liveRingId: 7,
      liveOrdinalStart: 0,
      liveOrdinalEnd: 1,
      fileSha256: sha256.convert([1, 17]).toString());

  test('R16 indexed digest is authority only for current owner and exact device', () async {
    await WalFileManager.saveWals([await row()]);
    expect(await walFileManagerCustodyValidator(liveRef()), isTrue);
    expect(await walFileManagerCustodyValidator(liveRef(device: 'another-device')), isFalse);
    SharedPreferencesUtil().uid = 'other';
    expect(await walFileManagerCustodyValidator(liveRef()), isFalse);
    expect(await walFileManagerCustodyValidator(liveRef(owner: null)), isFalse);
  });

  test('R16 ownerless legacy checkpoint saved by previous build cannot replay', () async {
    await WalFileManager.saveWals([await row()]);
    final store = PendantCustodyStore(directoryProvider: () async => Directory('${dir.path}/custody'));
    final checkpoint = RingCustodyCheckpoint(
        deviceId: 'device',
        ringId: 7,
        reportedReadSeq: 100,
        reportedWriteSeq: 110,
        durableSeq: 101,
        liveRanges: [
          LiveRangeProof(
              startSeq: 100, endSeq: 101, startLiveOrdinal: 0, endLiveOrdinal: 1, wals: [liveRef(owner: null)])
        ]);
    await store.saveJson('device', checkpoint.toJson());
    final custody = PendantRingCustody(store: store);
    final replay = <int>[];
    await custody.beginConnection('device', 1, v1Info(readSeq: 100, writeSeq: 110), replayAdvance: (seq) async {
      replay.add(seq);
      return 0;
    });
    expect(replay, isEmpty);
    expect(await custody.validatedRecordRanges('device', 1, 7), isEmpty);
    await custody.flush();
  });

  test('R16 indexed empty marker survives restart; missing index and corrupt marker retain', () async {
    final bytes = utf8.encode(jsonEncode(
        {'kind': 'empty_ring_records_v1', 'device': 'device', 'ring': 7, 'start': 100, 'end': 101, 'owner': 'owner'}));
    await File('${dir.path}/empty.ring-empty').writeAsBytes(bytes, flush: true);
    final marker = Wal(
        codec: BleAudioCodec.opus,
        timerStart: 1000,
        seconds: 0,
        totalFrames: 0,
        storage: WalStorage.disk,
        status: WalStatus.synced,
        device: 'device',
        ownerUid: 'owner',
        filePath: 'empty.ring-empty',
        downloadRingId: 7,
        downloadSeqStart: 100,
        downloadSeqEnd: 101,
        downloadFileBytes: bytes.length,
        fileSha256: sha256.convert(bytes).toString());
    final ref = CustodyWalRef(
        fileName: 'empty.ring-empty',
        bytes: bytes.length,
        frames: 0,
        ownerUid: 'owner',
        downloadDeviceId: 'device',
        downloadRingId: 7,
        downloadSeqStart: 100,
        downloadSeqEnd: 101,
        fileSha256: marker.fileSha256);
    expect(await walFileManagerCustodyValidator(ref), isFalse);
    await WalFileManager.saveWals([marker]);
    expect(await walFileManagerCustodyValidator(ref), ringDrainRecoveryEnabled);
    final store = PendantCustodyStore(directoryProvider: () async => Directory('${dir.path}/custody'));
    final custody = PendantRingCustody(store: store);
    final replay = <int>[];
    await custody.beginConnection('device', 1, v1Info(readSeq: 100, writeSeq: 110), replayAdvance: (seq) async {
      replay.add(seq);
      return 0;
    });
    expect(replay, ringDrainRecoveryEnabled ? [101] : isEmpty);
    await custody.flush();
    final corrupt = List<int>.from(bytes)..[0] = 33;
    await File('${dir.path}/empty.ring-empty').writeAsBytes(corrupt, flush: true);
    expect(await walFileManagerCustodyValidator(ref), isFalse);
  });
}
