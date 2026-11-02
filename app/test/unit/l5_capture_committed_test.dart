import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/capture_committed_event.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/capture_committed_journal.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_upload_batch.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import '../support/custody_test_helpers.dart';
import '../support/refactor_flag_adapter.dart';

const root = '01234567-89ab-cdef-0123-456789abcdef';
CaptureCommittedEvent receipt(int start, int end,
        {String epoch = '0', String channel = 'mono', String session = 'session'}) =>
    CaptureCommittedEvent(
        conversationId: 'conversation',
        captureRoot: root,
        channel: channel,
        clockEpoch: epoch,
        recordingSessionId: session,
        sourceStart: start,
        sourceEnd: end);
Wal wal() => Wal(
    timerStart: 100,
    codec: BleAudioCodec.pcm16,
    sampleRate: 16000,
    seconds: 1,
    totalFrames: 100,
    ownerUid: 'owner',
    captureRoot: root,
    sourceFrameStart: 0,
    sourceClockEpoch: 0,
    recordingSessionId: 'session',
    conversationId: 'conversation',
    storage: WalStorage.disk,
    status: WalStatus.miss,
    device: 'phone',
    filePath: 'audio_phone_pcm16_16000_1_100.bin');
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;
  setUp(() async {
    directory = await custodyDirectory();
  });
  tearDown(() async {
    AnalyticsManager.resetForTesting();
    await directory.delete(recursive: true);
  });
  test('cached serving and deleting opt-ins fail closed across an identity change', () async {
    final adapter = await setRefactorFlags({'clients_refactor': true});
    expect(AnalyticsManager().refactorClientsEnabled('clients_refactor'), isTrue);
    adapter.onCachedRead = () => AnalyticsManager().bindIdentity('successor');
    expect(AnalyticsManager().refactorClientsEnabled('clients_refactor'), isFalse);
    expect(await AnalyticsManager().isBooleanFeatureEnabled('custody_capture_committed_release'), isFalse);
  });
  test('socket parser validates ranges and preserves source identity', () {
    final event = MessageEvent.fromJson(receipt(0, 100).toJson());
    expect(event, isA<CaptureCommittedEvent>());
    expect((event as CaptureCommittedEvent).sourceEnd, 100);
    expect(MessageEvent.fromJson({...receipt(0, 100).toJson(), 'source_end': 0}), isA<UnknownEvent>());
  });
  test('journal unions exact ranges durably, rejecting gaps and foreign identities', () async {
    final journal = CaptureCommittedJournal(() async => directory);
    final copy = wal();
    await journal.record('owner', receipt(0, 50));
    await journal.record('owner', receipt(51, 100));
    expect(await journal.covers('owner', copy), isFalse);
    await journal.record('owner', receipt(40, 60));
    await journal.record('owner', receipt(40, 60));
    expect(await CaptureCommittedJournal(() async => directory).covers('owner', copy), isTrue);
    expect(await journal.covers('other', copy), isFalse);
    copy.sourceClockEpoch = 1;
    expect(await journal.covers('owner', copy), isFalse);
    copy.sourceClockEpoch = 0;
    copy.recordingSessionId = 'other';
    expect(await journal.covers('owner', copy), isFalse);
  });
  for (final enabled in [false, true]) {
    test('ledger receipt release is explicit opt-in ($enabled), and never deletes the file', () async {
      await setRefactorFlags({'custody_capture_committed_release': enabled});
      final ledger = await custodyLedger();
      final copy = wal();
      final file = File('${directory.path}/${copy.filePath}');
      await file.writeAsBytes([1, 0, 0, 0, 1]);
      ledger.testWals = [copy];
      await ledger.recordCaptureCommitted(receipt(0, 50));
      expect(copy.status, WalStatus.miss);
      await ledger.recordCaptureCommitted(receipt(50, 100));
      expect(copy.status, enabled ? WalStatus.synced : WalStatus.miss);
      expect(copy.syncedAt > 0, enabled);
      expect(await file.exists(), isTrue);
      final restored = await custodyLedger();
      final saved = (await restored.getAllWals()).single;
      expect(saved.syncedAt > 0, enabled);
    });
  }
  test('serving commitment overrides heuristic coverage only with complete proof', () async {
    await setRefactorFlags({'custody_capture_committed_release': true});
    final ledger = await custodyLedger();
    final copy = wal();
    ledger.testWals = [copy];
    await ledger.confirmSessionTranscription(100, 'conversation', transcriptSpans: [(0, 1000)]);
    expect(copy.status, WalStatus.miss);
    expect(copy.keptForTranscriptRecovery, isTrue);
  });
  for (final flush in [false, true]) {
    test('index save failure reverts committed release before retention (flush=$flush)', () async {
      await setRefactorFlags({'custody_capture_committed_release': true});
      var fail = false;
      final ledger = await custodyLedger(persist: (_) async {
        if (fail) throw StateError('synthetic save failure');
      });
      final copy = wal();
      final file = File('${directory.path}/${copy.filePath}');
      await file.writeAsBytes([1, 0, 0, 0, 1]);
      ledger.testWals = [copy];
      fail = true;
      if (flush) {
        await ledger.captureCommits.record('owner', receipt(0, 100));
        await expectLater(ledger.syncAll(), throwsStateError);
      } else {
        await expectLater(ledger.recordCaptureCommitted(receipt(0, 100)), throwsStateError);
      }
      expect(copy.status, WalStatus.miss);
      expect(copy.syncedAt, 0);
      expect(copy.keptForTranscriptRecovery, isTrue);
      expect(await file.exists(), isTrue);
      await ledger.enforceRetentionPolicyForTesting();
      expect(await file.exists(), isTrue);
    });
  }
  test('held, local-only, unstamped and in-flight WALs cannot release', () async {
    await setRefactorFlags({'custody_capture_committed_release': true});
    final ledger = await custodyLedger();
    final copies = [
      wal()..holdForUser = true,
      wal()..onDeviceOnly = true,
      wal()..sourceFrameStart = null,
      wal()..isSyncing = true,
      wal()..ownerUid = 'other',
      wal()..channel = 2
    ];
    ledger.testWals = copies;
    await ledger.recordCaptureCommitted(receipt(0, 100));
    expect(copies.every((copy) => copy.status == WalStatus.miss), isTrue);
  });
  test('safety-WAL uploads already carry S1 ordinals, never invented from time', () {
    final copy = wal();
    final file = File('${directory.path}/${copy.filePath}');
    final header = captureEvidenceUploadHeader([copy], [file]);
    expect(header, isNotNull);
    final claim = (jsonDecode(header!) as Map)['files'][0] as Map;
    expect(claim['source_frame_start'], 0);
    expect(claim['frame_count'], 100);
    expect(claim['clock_epoch'], 0);
    copy.sourceFrameStart = null;
    expect(captureEvidenceUploadHeader([copy], [file]), isNull);
  });
}
