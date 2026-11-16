import 'dart:convert';
import 'dart:async';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/wals/native_recording_intake.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/on_device/on_device_overflow_intake.dart';
import 'package:omi/pages/settings/sign_out.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import '../support/custody_test_helpers.dart';

class _DelayedLedger extends LocalWalSyncImpl {
  _DelayedLedger() : super(CustodyListener());
  final blocked = Completer<void>();
  bool first = true;
  @override
  Future<void> intakeNativeRecordings() async {
    final uid = SharedPreferencesUtil().uid;
    if (first) {
      first = false;
      await blocked.future;
      if (uid != SharedPreferencesUtil().uid) return;
    }
    await super.intakeNativeRecordings();
  }
}

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
    await NativeRecordingIntake(ledger).scan();
    expect(await ledger.getAllWals(), isEmpty);
  });

  test('corrupt legacy ownership defers old files repeatedly but admits new files including overflow', () async {
    await audio(name);
    final owners = File('${dir.path}/omibatch_owners.json');
    await owners.writeAsString('{broken');
    final boundary = DateTime.now().subtract(const Duration(minutes: 1));
    await owners.setLastModified(boundary);
    final newer = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final newName = 'audio_omibatchphone_opus_16000_1_fs320_$newer.bin';
    final overflow = 'audio_omibatchoverflow_opus_16000_1_fs320_$newer.bin';
    await audio(newName);
    await audio(overflow);
    final ledger = await custodyLedger();
    await ledger.intakeNativeRecordings();
    await ledger.intakeNativeRecordings();
    expect(ledger.nativeWalForFileName(name), isNull);
    expect(await File('${dir.path}/$name').exists(), isTrue);
    expect(ledger.nativeWalForFileName(newName)!.ownerUid, 'owner');
    expect(ledger.nativeWalForFileName(overflow)!.onDeviceOnly, isTrue);
    expect(await owners.readAsString(), '{broken');
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
  test('deferred legacy migration does not hide rows already owned by the ledger', () async {
    await audio(name);
    final ledger = await custodyLedger();
    await ledger.intakeNativeRecordings();
    await File('${dir.path}/omibatch_owners.json').writeAsString('{broken');
    final view = LocalRecordingsProvider(ledger: ledger, initialize: false);
    await view.refresh();
    expect(view.recordings.single.fileName, name);
    expect(view.isLoading, isFalse);
    view.dispose();
  });

  test('waiting recordings survive pre-upgrade unstamped index, signed-out cold start, and same-account re-login',
      () async {
    await audio(name);
    final ledger = await custodyLedger();
    await ledger.intakeNativeRecordings();
    // Simulate a pre-upgrade wals.json entry whose ownerUid was not yet stamped on disk.
    final wal = (await ledger.getAllWals()).single;
    wal.ownerUid = null;
    await ledger.persistRetryMetadata(wal);

    // Cold-start a fresh ledger and provider while signed out (e.g. after app update cleared auth).
    SharedPreferencesUtil().uid = '';
    final coldLedger = await custodyLedger();
    expect(await coldLedger.getAllWals(), isEmpty, reason: 'unstamped batch rows cannot enter a drain before intake');
    final coldView = LocalRecordingsProvider(ledger: coldLedger, initialize: false);
    await coldView.refresh();
    expect(coldView.recordings, isEmpty);

    // Sign back into the same account on the cold-started singleton ledger/provider.
    SharedPreferencesUtil().uid = 'owner';
    await coldView.refresh();
    expect(coldView.recordings.single.fileName, name);
    expect((await coldLedger.getAllWals()).single.ownerUid, 'owner');

    // Also verify in-session sign-out followed by same-account sign-in rehydrates from retired/foreign custody.
    coldLedger.clearUserData();
    coldView.clearUserData();
    SharedPreferencesUtil().uid = '';
    expect(coldView.recordings, isEmpty);

    SharedPreferencesUtil().uid = 'owner';
    await coldView.refresh();
    expect(coldView.recordings.single.fileName, name);
    coldView.dispose();
  });
  for (final unstampedOwner in <String?>[null, '', 'legacy']) {
    test(
        'upgrade receipts for $unstampedOwner survive sign-out, foreign login and same-owner restart without re-upload',
        () async {
      await audio(name);
      final ledger = await custodyLedger();
      await ledger.intakeNativeRecordings();
      final wal = (await ledger.getAllWals()).single;
      wal.ownerUid = unstampedOwner;
      await ledger.persistRetryMetadata(wal);
      await File('${dir.path}/omibatch_owners.json').writeAsString(jsonEncode({name: 'owner'}));
      await SharedPreferencesUtil().saveString('localRecordingJobs', jsonEncode({name: 'accepted-job'}));
      await SharedPreferencesUtil().saveString('localRecordingJobsCorrupt', 'quarantined');
      ledger.clearUserData();
      await clearPreferencesForSignOut();
      expect(SharedPreferencesUtil().getString('localRecordingJobs'), contains('accepted-job'));
      expect(SharedPreferencesUtil().getString('localRecordingJobsCorrupt'), 'quarantined');
      SharedPreferencesUtil().uid = 'other';
      final restarted = await custodyLedger();
      final view = LocalRecordingsProvider(ledger: restarted, initialize: false);
      await view.refresh();
      expect(view.recordings, isEmpty);
      expect(await restarted.getAllWals(), isEmpty);
      expect(restarted.testForeignWals.single.ownerUid, 'owner');
      expect(restarted.testForeignWals.single.jobId, 'accepted-job');
      restarted.clearUserData();
      view.clearUserData();
      SharedPreferencesUtil().uid = 'owner';
      await view.refresh();
      expect(view.recordings.single.fileName, name);
      expect(view.recordings.single.state.name, 'processing');
      final restored = (await restarted.getAllWals()).single;
      expect(restored.status, WalStatus.uploaded);
      expect(restored.jobId, 'accepted-job');
      expect(restored.holdForUser, isTrue);
      expect(await File('${dir.path}/$name').readAsBytes(), [1, 0, 0, 0, 5]);
      await view.refresh();
      expect(view.recordings, hasLength(1));
      view.dispose();
    });
  }

  test('indexed unstamped batch with corrupt ownership stays recoverable but unexposed', () async {
    await audio(name);
    final ledger = await custodyLedger();
    await ledger.intakeNativeRecordings();
    final wal = (await ledger.getAllWals()).single;
    wal.ownerUid = null;
    await ledger.persistRetryMetadata(wal);
    await File('${dir.path}/omibatch_owners.json').writeAsString('{broken');
    final view = LocalRecordingsProvider(ledger: ledger, initialize: false);
    await view.refresh();
    expect(view.recordings, isEmpty);
    expect(await ledger.getAllWals(), isEmpty);
    expect(ledger.testForeignWals.single.ownerUid, isNull);
    expect(await File('${dir.path}/$name').exists(), isTrue);
    expect(await File('${dir.path}/omibatch_owners.json').readAsString(), '{broken');
    view.dispose();
  });
  test('post-auth refresh does not join an obsolete signed-out refresh', () async {
    await audio(name);
    final initial = await custodyLedger();
    await initial.intakeNativeRecordings();
    SharedPreferencesUtil().uid = '';
    final ledger = _DelayedLedger();
    await ledger.loadForOnDeviceWorker();
    final view = LocalRecordingsProvider(ledger: ledger, initialize: false);
    final oldRefresh = view.refresh();
    SharedPreferencesUtil().uid = 'owner';
    await view.refresh().timeout(const Duration(seconds: 2));
    expect(view.recordings.single.fileName, name);
    ledger.blocked.complete();
    await oldRefresh;
    expect(view.recordings.single.fileName, name);
    view.dispose();
  });
  for (final unstampedOwner in <String?>[null, '', 'legacy']) {
    test('headless overflow intake restores $unstampedOwner rows without a Home refresh', () async {
      const overflow = 'audio_omibatchoverflow_opus_16000_1_fs320_1720000000.bin';
      await audio(overflow);
      final initial = await custodyLedger();
      await intakeOnDeviceOverflow(initial);
      final wal = (await initial.getAllWals()).single;
      wal.ownerUid = unstampedOwner;
      await initial.persistRetryMetadata(wal);
      await File('${dir.path}/omibatch_owners.json').writeAsString(jsonEncode({overflow: 'owner'}));
      final restarted = await custodyLedger();
      expect(await restarted.getAllWals(), isEmpty);
      await intakeOnDeviceOverflow(restarted);
      final restored = (await restarted.getAllWals()).single;
      expect(restored.ownerUid, 'owner');
      expect(restored.onDeviceOnly, isTrue);
      expect(isAutoUploadEligible(restored), isFalse);
      expect(await File('${dir.path}/$overflow').exists(), isTrue);
    });
  }
  test('an uninitialized view refresh remains a no-op without a ledger service', () async {
    final view = LocalRecordingsProvider(initialize: false);
    await view.refresh();
    expect(view.recordings, isEmpty);
    expect(view.isLoading, isFalse);
    view.dispose();
  });
}
