import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

void main() {
  late Directory tempDir;

  Wal makeUploadedWal({required int timerStart, required String fileName}) => Wal(
        timerStart: timerStart,
        codec: BleAudioCodec.opus,
        seconds: 45,
        status: WalStatus.uploaded,
        storage: WalStorage.disk,
        device: 'omi',
        filePath: fileName,
      )..jobId = 'job-speech-without-text';

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({
      'autoRemoveSyncedCopies': true,
      'autoRemoveSyncedCopiesDays': 30,
    });
    await SharedPreferencesUtil.init();
    tempDir = await Directory.systemTemp.createTemp('wal_speech_without_text_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    await WalFileManager.init();
    SyncRateLimiter.instance.clear();
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    SyncRateLimiter.instance.clear();
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  test('SyncLocalFilesResponse parses speech_without_text from wire JSON', () {
    final parsed = SyncLocalFilesResponse.fromJson({
      'new_memories': <String>[],
      'updated_memories': <String>[],
      'speech_without_text': <String>['audio_1700000000.bin'],
      'failed_segments': 0,
      'total_segments': 2,
      'errors': <String>[],
    });
    expect(parsed.speechWithoutText, ['audio_1700000000.bin']);
  });

  test('reconcileUploadedWals marks only speech_without_text files and keeps them out of 30-day auto-remove', () async {
    final silentFile = File('${tempDir.path}/audio_1700000000.bin')..writeAsBytesSync([1, 2, 3]);
    final transcribedFile = File('${tempDir.path}/audio_1700000100.bin')..writeAsBytesSync([4, 5, 6]);

    final status = SyncJobStatusResponse(
      jobId: 'job-speech-without-text',
      status: 'completed',
      totalSegments: 2,
      processedSegments: 2,
      successfulSegments: 2,
      failedSegments: 0,
      result: SyncLocalFilesResponse(
        newConversationIds: const ['conv-1'],
        updatedConversationIds: const [],
        speechWithoutText: const ['audio_1700000000.bin'],
      ),
    );

    var now = DateTime.fromMillisecondsSinceEpoch(1700000500 * 1000);
    final sync = LocalWalSyncImpl(
      _Listener(),
      now: () => now,
      jobStatusFetcher: (_) async => SyncJobFetch(SyncJobFetchOutcome.ok, status),
    );

    final silentWal = makeUploadedWal(timerStart: 1700000000, fileName: 'audio_1700000000.bin');
    final transcribedWal = makeUploadedWal(timerStart: 1700000100, fileName: 'audio_1700000100.bin');
    sync.testWals = [silentWal, transcribedWal];

    final reconciled = await sync.reconcileUploadedWals();
    expect(reconciled.speechWithoutText, ['audio_1700000000.bin']);
    expect(silentWal.status, WalStatus.synced);
    expect(silentWal.speechWithoutText, isTrue);
    expect(walDeletionAllowed(silentWal), isTrue);

    expect(transcribedWal.status, WalStatus.synced);
    expect(transcribedWal.speechWithoutText, isFalse);
    expect(walDeletionAllowed(transcribedWal), isFalse);

    // Advance clock past the 30-day retention window.
    now = now.add(const Duration(days: 31));
    final removed = await sync.applySyncedCopyRetention();

    expect(removed, 1);
    expect(silentFile.existsSync(), isTrue, reason: 'speech_without_text audio must not be auto-removed after 30 days');
    expect(transcribedFile.existsSync(), isFalse, reason: 'normal synced copy is eligible for 30-day auto-remove');
    expect(sync.testWals.map((w) => w.id), [silentWal.id]);
  });

  test('Wal round-trips speechWithoutText in JSON and persistentFingerprint', () {
    final wal = Wal(
      timerStart: 1700000000,
      codec: BleAudioCodec.opus,
      seconds: 30,
      status: WalStatus.synced,
      storage: WalStorage.disk,
      filePath: 'audio_1700000000.bin',
    );
    final beforeFp = wal.persistentFingerprint;
    wal.speechWithoutText = true;
    expect(wal.persistentFingerprint, isNot(equals(beforeFp)));

    final restored = Wal.fromJson(wal.toJson());
    expect(restored.speechWithoutText, isTrue);
    expect(restored.persistentFingerprint, wal.persistentFingerprint);
  });
}
