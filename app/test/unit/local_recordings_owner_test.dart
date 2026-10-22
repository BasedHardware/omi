import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/wals/native_recording_intake.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import '../support/custody_test_helpers.dart';

void main() {
  late Directory dir;
  setUp(() async {
    dir = await custodyDirectory();
  });
  tearDown(() async {
    await dir.delete(recursive: true);
  });
  const name = 'audio_omibatchphone_opus_16000_1_fs320_1720000000.bin';
  Future<void> audio(String name) => File('${dir.path}/$name').writeAsBytes([1, 0, 0, 0, 5]);

  test('intake stamps the signed-in owner once and survives an account switch', () async {
    await audio(name);
    final ledger = await custodyLedger();
    final intake = NativeRecordingIntake(ledger);
    await Future.wait([intake.scan(), intake.scan()]);
    expect((await ledger.getAllWals()).single.ownerUid, 'owner');
    SharedPreferencesUtil().uid = 'other';
    final other = await custodyLedger();
    await NativeRecordingIntake(other).scan();
    expect(await other.getAllWals(), isEmpty);
    expect(other.testForeignWals.single.ownerUid, 'owner');
    expect(await File('${dir.path}/$name').exists(), isTrue);
  });

  test('legacy owners migrate into parked ledger custody without reassignment', () async {
    await audio(name);
    await File('${dir.path}/omibatch_owners.json').writeAsString(jsonEncode({name: 'other'}));
    final ledger = await custodyLedger();
    await NativeRecordingIntake(ledger).scan();
    expect(await ledger.getAllWals(), isEmpty);
    expect(ledger.testForeignWals.single.ownerUid, 'other');
    expect(await File('${dir.path}/omibatch_owners.json').exists(), isFalse);
  });

  test('signed-out and corrupt legacy ownership both defer intake', () async {
    await audio(name);
    final ledger = await custodyLedger();
    SharedPreferencesUtil().uid = '';
    await NativeRecordingIntake(ledger).scan();
    expect(await ledger.getAllWals(), isEmpty);
    SharedPreferencesUtil().uid = 'owner';
    await File('${dir.path}/omibatch_owners.json').writeAsString('{broken');
    await expectLater(NativeRecordingIntake(ledger).scan(), throwsFormatException);
    expect(await ledger.getAllWals(), isEmpty);
  });

  test('Watch takes only its committed receipt owner; missing receipts stay untouched', () async {
    const session = '0123456789abcdef0123456789abcdef';
    const watch = 'audio_omibatchwatch${session}s0_pcm16_16000_1_fs160_1720000000.bin';
    await audio(watch);
    final ledger = await custodyLedger();
    await NativeRecordingIntake(ledger).scan();
    expect(await ledger.getAllWals(), isEmpty);
    await Directory('${dir.path}/.watch-receipts').create();
    await File('${dir.path}/.watch-receipts/$watch').writeAsString(jsonEncode({
      'metadata': {'version': 1, 'sessionID': session, 'segment': 0, 'startedAt': 1720000000, 'ownerUID': 'other'},
      'digest': 'a' * 64,
    }));
    await NativeRecordingIntake(ledger).scan();
    expect(await ledger.getAllWals(), isEmpty);
    expect(ledger.testForeignWals.single.ownerUid, 'other');
    expect(await File('${dir.path}/$watch').exists(), isTrue);
  });
  test('overflow ownership reaches phone-only custody before migration removes the owners file', () async {
    const overflow = 'audio_omibatchoverflow_opus_16000_1_fs320_1720000000.bin';
    await audio(overflow);
    await audio(name);
    await File('${dir.path}/omibatch_owners.json').writeAsString(jsonEncode({overflow: 'other', name: 'owner'}));
    final ledger = await custodyLedger();
    await ledger.intakeNativeRecordings();
    expect((await ledger.getAllWals()).single.filePath, name);
    final held = ledger.testForeignWals.single;
    expect(held.filePath, overflow);
    expect(held.onDeviceOnly, isTrue);
    expect(held.ownerUid, 'other');
    expect(isAutoUploadEligible(held), isFalse);
    expect(await File('${dir.path}/omibatch_owners.json').exists(), isFalse);
    await ledger.intakeNativeRecordings();
    expect(ledger.testForeignWals.length, 1);
  });
}
