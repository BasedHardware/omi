import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:crypto/crypto.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/capture_committed_event.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
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
// Same envelope the authenticated mono Listen socket sends after both objects commit.
AudioCustodyEvent audioReceipt(int start, int end, {int payload = 1}) {
  const archive = '0123456789abcdef0123456789abcdef';
  final hash = sha256.convert([payload]).toString();
  final suffix = 'owner/conversation/2026112311/0/$archive/$start/$hash.bin';
  return AudioCustodyEvent.parse({
    'type': 'audio_custody',
    'channel': '0',
    'capture_root': archive,
    'recording_session_id': 'session',
    'receipt': <String, dynamic>{
      'bucket': 'archive',
      'path': 'raw-live/$suffix',
      'generation': '7',
      'sha256': hash,
      'manifest_path': 'audio-outbox/$suffix',
      'manifest_generation': '8',
      'manifest_sha256': hash,
      'conversation_id': 'conversation',
      'start': 100,
      'samples': end - start,
      'sample_rate': 16000,
    },
    'frames': [
      for (int ordinal = start; ordinal < end; ordinal++)
        <String, dynamic>{
          'sequence': ordinal,
          'byte_offset': ordinal - start,
          'bytes': 1,
          'samples': 1,
          'start': 100.0,
          'gap_before': false,
          'sha256': hash,
          'source': <String, dynamic>{'capture_root': root, 'clock_epoch': 0, 'source_frame': ordinal}
        },
    ],
  })!;
}

Future<File> writeWal(Directory directory, Wal copy) async {
  final file = File('${directory.path}/${copy.filePath}');
  await file.writeAsBytes([
    for (int i = 0; i < copy.totalFrames; i++) ...[1, 0, 0, 0, 1]
  ]);
  return file;
}

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
    expect(await AnalyticsManager().isBooleanFeatureEnabled('custody_durable_audio_release'), isFalse);
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
    await writeWal(directory, copy);
    await journal.record('owner', receipt(0, 100));
    expect(await journal.covers('owner', copy), isFalse, reason: 'transcript-only rows carry no audio proof');
    await journal.record('owner', audioReceipt(0, 50));
    await journal.record('owner', audioReceipt(51, 100));
    expect(await journal.covers('owner', copy), isFalse);
    await journal.record('owner', audioReceipt(40, 60));
    await journal.record('owner', audioReceipt(40, 60));
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
      await setRefactorFlags({'custody_durable_audio_release': enabled});
      final ledger = await custodyLedger();
      final copy = wal();
      final file = await writeWal(directory, copy);
      ledger.testWals = [copy];
      await ledger.persistRetryMetadata(copy); // Normal intake already persisted this pending WAL.
      await ledger.recordCustodyReceipt(audioReceipt(0, 50), owner: 'owner');
      expect(copy.status, WalStatus.miss);
      await ledger.recordCustodyReceipt(audioReceipt(50, 100), owner: 'owner');
      expect(copy.status, enabled ? WalStatus.synced : WalStatus.miss);
      expect(copy.syncedAt > 0, enabled);
      expect(await file.exists(), isTrue);
      final restored = await custodyLedger();
      final saved = (await restored.getAllWals()).single;
      expect(saved.syncedAt > 0, enabled);
    });
  }
  test('durable proof arriving before the WAL suppresses both single and batch upload after restart', () async {
    await setRefactorFlags({'custody_durable_audio_release': true});
    final ledger = await custodyLedger();
    final copy = wal();
    await writeWal(directory, copy);
    await ledger.recordCustodyReceipt(audioReceipt(0, 100), owner: 'owner');
    ledger.testWals = [copy];
    await ledger.persistRetryMetadata(copy);
    final restarted = await custodyLedger();
    final pending = (await restarted.getAllWals()).single;
    expect(await restarted.syncWal(wal: pending), isNull);
    expect(pending.status, WalStatus.synced);
    expect(await restarted.syncAll(), isNull);
    expect((await (await custodyLedger()).getAllWals()).single.syncedAt, greaterThan(0));
  });
  test('receipt referencing different bytes or received for another owner preserves upload eligibility', () async {
    await setRefactorFlags({'custody_durable_audio_release': true});
    final ledger = await custodyLedger();
    final copy = wal();
    final file = await writeWal(directory, copy);
    ledger.testWals = [copy];
    await ledger.recordCustodyReceipt(audioReceipt(0, 100), owner: 'other');
    await ledger.recordCustodyReceipt(audioReceipt(0, 100, payload: 2), owner: 'owner');
    expect(copy.status, WalStatus.miss);
    expect(copy.syncedAt, 0);
    expect(await file.exists(), isTrue);
  });
  test('serving commitment overrides heuristic coverage only with complete proof', () async {
    await setRefactorFlags({'custody_durable_audio_release': true});
    final ledger = await custodyLedger();
    final copy = wal();
    ledger.testWals = [copy];
    await ledger.confirmSessionTranscription(100, 'conversation', transcriptSpans: [(0, 1000)]);
    expect(copy.status, WalStatus.miss);
    expect(copy.keptForTranscriptRecovery, isTrue);
  });
  test('live custom STT releases covered phone backups without server frame receipts and keeps uncovered ones',
      () async {
    await setRefactorFlags({'custody_durable_audio_release': true});
    final ledger = await custodyLedger();
    final covered = wal();
    final uncovered = wal()
      ..timerStart = 500
      ..filePath = 'audio_phone_pcm16_16000_1_500.bin';
    ledger.testWals = [covered, uncovered];
    await ledger.confirmSessionTranscription(
      100,
      'conversation',
      transcriptSpans: [(95, 105)],
      allowTranscriptCoverageFallback: true,
    );
    expect(covered.status, WalStatus.synced);
    expect(covered.syncedAt, greaterThan(0));
    expect(covered.keptForTranscriptRecovery, isFalse);
    expect(uncovered.status, WalStatus.miss);
    expect(uncovered.keptForTranscriptRecovery, isTrue);
  });
  test('Custom STT coverage cannot release held, on-device, foreign, unlinked or interrupted audio', () async {
    await setRefactorFlags({'custody_durable_audio_release': true});
    final ledger = await custodyLedger();
    final copies = [
      wal()..holdForUser = true,
      wal()..onDeviceOnly = true,
      wal()..ownerUid = 'other',
      wal()..conversationId = null
    ];
    ledger.testWals = copies;
    await ledger.confirmSessionTranscription(100, 'conversation',
        transcriptSpans: [(95, 105)], allowTranscriptCoverageFallback: true);
    expect(copies.every((w) => w.status == WalStatus.miss), isTrue);
    final interrupted = wal();
    ledger.testWals = [interrupted];
    await ledger.confirmSessionTranscription(100, 'conversation',
        transcriptSpans: [(95, 105)], failClosedReason: 'needs_repair', allowTranscriptCoverageFallback: true);
    expect(interrupted.status, WalStatus.miss);
  });
  test('Custom STT coverage persistence failure retains the only audio copy', () async {
    await setRefactorFlags({'custody_durable_audio_release': true});
    var fail = false;
    final ledger = await custodyLedger(persist: (_) async {
      if (fail) throw StateError('disk full');
    });
    final copy = wal();
    final file = File('${directory.path}/${copy.filePath}');
    await file.writeAsBytes([1, 0, 0, 0, 1]);
    ledger.testWals = [copy];
    fail = true;
    await expectLater(
        ledger.confirmSessionTranscription(100, 'conversation',
            transcriptSpans: [(95, 105)], allowTranscriptCoverageFallback: true),
        throwsStateError);
    expect(copy.status, WalStatus.miss);
    expect(copy.syncedAt, 0);
    await ledger.enforceRetentionPolicyForTesting();
    expect(await file.exists(), isTrue);
  });
  test('delayed normal-STT confirmation ignores current custom STT preference and flag-off ignores receipts', () async {
    await setRefactorFlags({'custody_durable_audio_release': true});
    await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.geminiLive, apiKey: 'gemini-key'),
    );
    addTearDown(() => SharedPreferencesUtil().saveCustomSttConfig(const CustomSttConfig(provider: SttProvider.omi)));
    final ledger = await custodyLedger();
    final normalSessionWal = wal();
    ledger.testWals = [normalSessionWal];
    await ledger.confirmSessionTranscription(100, 'conversation', transcriptSpans: [(95, 105)]);
    expect(normalSessionWal.status, WalStatus.miss);
    expect(normalSessionWal.keptForTranscriptRecovery, isTrue);

    await setRefactorFlags({'custody_durable_audio_release': false});
    final receiptOnlyWal = wal();
    ledger.testWals = [receiptOnlyWal];
    await ledger.captureCommits.record('owner', audioReceipt(0, 100));
    await ledger.confirmSessionTranscription(100, 'conversation', transcriptSpans: [(500, 600)]);
    expect(receiptOnlyWal.status, WalStatus.miss);
    expect(receiptOnlyWal.keptForTranscriptRecovery, isTrue);
  });
  for (final flush in [false, true]) {
    test('index save failure reverts committed release before retention (flush=$flush)', () async {
      await setRefactorFlags({'custody_durable_audio_release': true});
      var fail = false;
      final ledger = await custodyLedger(persist: (_) async {
        if (fail) throw StateError('synthetic save failure');
      });
      final copy = wal();
      final file = await writeWal(directory, copy);
      ledger.testWals = [copy];
      fail = true;
      if (flush) {
        await ledger.captureCommits.record('owner', audioReceipt(0, 100));
        await expectLater(ledger.syncAll(), throwsStateError);
      } else {
        await expectLater(ledger.recordCustodyReceipt(audioReceipt(0, 100), owner: 'owner'), throwsStateError);
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
    await setRefactorFlags({'custody_durable_audio_release': true});
    final ledger = await custodyLedger();
    await writeWal(directory, wal());
    final copies = [
      wal()..holdForUser = true,
      wal()..onDeviceOnly = true,
      wal()..sourceFrameStart = null,
      wal()..isSyncing = true,
      wal()..ownerUid = 'other',
      wal()..channel = 2
    ];
    ledger.testWals = copies;
    await ledger.recordCustodyReceipt(audioReceipt(0, 100), owner: 'owner');
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
