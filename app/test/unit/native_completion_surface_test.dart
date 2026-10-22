import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/wals/native_recording_intake.dart';
import 'package:omi/services/wals/wal.dart';
import '../support/custody_test_helpers.dart';

void main() {
  late Directory dir;
  const name = 'audio_omibatchphone_opus_16000_1_fs320_1720000000.bin';
  setUp(() async {
    dir = await custodyDirectory();
    await File('${dir.path}/$name').writeAsBytes([1, 0, 0, 0, 5]);
    await SharedPreferencesUtil().saveString('localRecordingJobs', jsonEncode({name: 'legacy-job'}));
  });
  tearDown(() async => dir.delete(recursive: true));

  test('a migrated queued job surfaces its confirmed conversation through the ledger completion hook', () async {
    final ledger = await custodyLedger(
        fetch: (id) async => SyncJobFetch(
            SyncJobFetchOutcome.ok,
            SyncJobStatusResponse(
                jobId: id,
                status: 'completed',
                result: SyncLocalFilesResponse(newConversationIds: ['conversation'], updatedConversationIds: []))));
    await NativeRecordingIntake(ledger).scan();
    final surfaced = <String>[];
    final done = Completer<void>();
    final view = LocalRecordingsProvider(
        ledger: ledger,
        surfaceConversations: (result) async {
          surfaced.addAll(result.newConversationIds);
          done.complete();
        });
    addTearDown(view.dispose);
    await view.refresh();
    expect(await File('${dir.path}/$name').exists(), isTrue);
    await ledger.reconcileUploadedWals();
    await done.future;
    expect(surfaced, ['conversation']);
    expect((await ledger.getAllWals()).single.status, WalStatus.synced);
    await ledger.reconcileUploadedWals();
    expect(surfaced, ['conversation'], reason: 'a finished job surfaces once');
  });

  test('a failed job with partial result IDs does not publish a completed Home conversation', () async {
    final ledger = await custodyLedger(
        fetch: (id) async => SyncJobFetch(
            SyncJobFetchOutcome.ok,
            SyncJobStatusResponse(
                jobId: id,
                status: 'failed',
                totalSegments: 1,
                failedSegments: 1,
                result: SyncLocalFilesResponse(newConversationIds: ['partial'], updatedConversationIds: []))));
    await NativeRecordingIntake(ledger).scan();
    final surfaced = <String>[];
    final view = LocalRecordingsProvider(
        ledger: ledger,
        surfaceConversations: (result) async {
          surfaced.addAll(result.newConversationIds);
        });
    addTearDown(view.dispose);
    await view.refresh();
    await ledger.reconcileUploadedWals();
    expect(surfaced, isEmpty);
    expect(ledger.conversationCompletions.value, isNull);
    expect(await File('${dir.path}/$name').exists(), isTrue);
  });
}
