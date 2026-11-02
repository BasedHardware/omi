import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/native_recording_intake.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import '../support/custody_test_helpers.dart';

void main() {
  late Directory dir;
  setUp(() async {
    dir = await custodyDirectory();
  });
  tearDown(() async {
    await dir.delete(recursive: true);
  });
  String name(String marker) => 'audio_${marker}_opus_16000_1_fs320_1720000000.bin';
  Future<void> audio(String marker) async {
    await File('${dir.path}/${name(marker)}').writeAsBytes([1, 0, 0, 0, 5]);
  }

  test('native intake is idempotent by filename, preserves metadata and skips overflow', () async {
    for (final marker in ['omibatchphone', 'omibatchphoneauto', 'omibatchlimitless', 'omibatchoverflow']) {
      await audio(marker);
    }
    final ledger = await custodyLedger();
    final intake = NativeRecordingIntake(ledger);
    await Future.wait(List.generate(3, (_) => intake.scan()));
    final wals = await ledger.getAllWals();
    expect(wals.length, 3);
    expect(wals.where((w) => w.holdForUser).single.device, 'omibatchphone');
    for (final w in wals) {
      expect(w.totalFrames, 1);
      expect(w.frameSize, 320);
      expect(w.sampleRate, 16000);
      expect(w.ownerUid, 'owner');
      expect(w.recordingSessionId, isNull);
    }
    final restored = await custodyLedger();
    await NativeRecordingIntake(restored).scan();
    expect((await restored.getAllWals()).length, 3);
  });

  test('legacy jobs transfer to shared poller once; migration sources removed only after save', () async {
    await audio('omibatchphone');
    await SharedPreferencesUtil().saveString('localRecordingJobs', jsonEncode({name('omibatchphone'): 'old-job'}));
    await File('${dir.path}/omibatch_owners.json').writeAsString(jsonEncode({name('omibatchphone'): 'owner'}));
    final ledger = await custodyLedger();
    await NativeRecordingIntake(ledger).scan();
    final wal = (await ledger.getAllWals()).single;
    expect(wal.status, WalStatus.uploaded);
    expect(wal.jobId, 'old-job');
    expect(wal.holdForUser, isTrue);
    expect(SharedPreferencesUtil().getString('localRecordingJobs'), isEmpty);
    expect(await File('${dir.path}/omibatch_owners.json').exists(), isFalse);
    await NativeRecordingIntake(ledger).scan();
    expect((await ledger.getAllWals()).single.jobId, 'old-job');
  });

  test('failed index save retains migration sources and retry completes without another WAL', () async {
    await audio('omibatchphone');
    await SharedPreferencesUtil().saveString('localRecordingJobs', jsonEncode({name('omibatchphone'): 'old-job'}));
    var fail = true;
    final ledger = await custodyLedger(persist: (_) async {
      if (fail) throw StateError('disk failure');
    });
    final intake = NativeRecordingIntake(ledger);
    await expectLater(intake.scan(), throwsStateError);
    expect(SharedPreferencesUtil().getString('localRecordingJobs'), isNotEmpty);
    fail = false;
    await intake.scan();
    expect((await ledger.getAllWals()).length, 1);
    expect((await ledger.getAllWals()).single.jobId, 'old-job');
    expect(SharedPreferencesUtil().getString('localRecordingJobs'), isEmpty);
  });

  test('malformed legacy jobs are quarantined once without blocking native intake', () async {
    await audio('omibatchphone');
    await SharedPreferencesUtil().saveString('localRecordingJobs', '{broken');
    final ledger = await custodyLedger();
    final intake = NativeRecordingIntake(ledger);
    await intake.scan();
    expect((await ledger.getAllWals()).single.holdForUser, isTrue);
    expect(SharedPreferencesUtil().getString('localRecordingJobsCorrupt'), '{broken');
    expect(SharedPreferencesUtil().getString('localRecordingJobs'), isEmpty);
    await intake.scan();
    expect((await ledger.getAllWals()).length, 1);
    expect(SharedPreferencesUtil().getString('localRecordingJobsCorrupt'), '{broken');
  });

  test('hold persists compatibly, never drains or repairs; accepted manual upload retains processing hold', () async {
    await audio('omibatchphone');
    var uploads = 0;
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
          uploads++;
          return UploadFilesResult.queued('job');
        });
    final ledger = await custodyLedger(gate: gate);
    await NativeRecordingIntake(ledger).scan();
    final wal = (await ledger.getAllWals()).single..conversationId = 'conversation';
    expect(Wal.fromJson(wal.toJson()).holdForUser, isTrue);
    expect(Wal.fromJson({...wal.toJson()}..remove('hold_for_user')).holdForUser, isFalse);
    expect(isAutoUploadEligible(wal), isFalse);
    expect(ledger.getOrphanedWals(), isEmpty);
    await ledger.syncAll();
    await ledger.syncLiveCaptureOnly();
    await ledger.confirmSessionTranscription(wal.timerStart, 'conversation');
    expect(wal.keptForTranscriptRecovery, isFalse);
    expect(uploads, 0);
    await ledger.syncWal(wal: wal);
    expect(uploads, 1);
    expect(wal.holdForUser, isTrue);
    expect(wal.status, WalStatus.uploaded);
  });

  test('a rejected manual request keeps the user hold', () async {
    await audio('omibatchphone');
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
                geolocation}) async =>
            throw StateError('offline'));
    final ledger = await custodyLedger(gate: gate);
    await NativeRecordingIntake(ledger).scan();
    final wal = (await ledger.getAllWals()).single;
    await expectLater(ledger.syncWal(wal: wal), throwsStateError);
    expect(wal.holdForUser, isTrue);
    expect(isAutoUploadEligible(wal), isFalse);
  });

  test('Home view lists only user-held WALs and follows ledger state', () async {
    for (final m in ['omibatch', 'omibatchphone', 'omibatchphoneauto', 'omibatchlimitless']) {
      await audio(m);
    }
    final ledger = await custodyLedger();
    await NativeRecordingIntake(ledger).scan();
    final view = LocalRecordingsProvider(ledger: ledger, initialize: false);
    addTearDown(view.dispose);
    await view.refresh();
    expect(view.recordings.map((r) => r.fileName).toSet(), {name('omibatch'), name('omibatchphone')});
    expect(view.recordings.every((r) => ledger.nativeWalForFileName(r.fileName)!.holdForUser), isTrue);
    final held = ledger.nativeWalForFileName(name('omibatch'))!;
    held.retryCount = 1;
    await view.refresh();
    expect(view.getById(held.filePath!)!.state.name, 'failed');
    await view.delete(view.getById(held.filePath!)!);
    expect(view.recordings.length, 1);
    expect(await File('${dir.path}/${held.filePath}').exists(), isFalse);
  });

  test('only the local ledger calls SyncUploadGate.upload anywhere in lib', () async {
    final offenders = <String>[];
    await for (final file in Directory('lib').list(recursive: true)) {
      if (file is! File || !file.path.endsWith('.dart') || file.path.endsWith('local_wal_sync.dart')) continue;
      final source = await file.readAsString();
      final gated = source.contains('SyncUploadGate') && RegExp(r'\.\s*upload\s*\(').hasMatch(source);
      final httpClient = file.path.endsWith('backend/http/api/conversations.dart');
      final rawCalls = !httpClient && RegExp(r'uploadLocalFilesV2\s*\(|fetchSyncJobStatus\s*\(').hasMatch(source);
      final rawPath = !httpClient &&
          !file.path.endsWith('backend/http/api_edge_throttle_telemetry.dart') &&
          source.contains('sync-local-files');
      final raw = rawCalls || rawPath;
      if (gated || raw) offenders.add(file.path);
    }
    expect(offenders, isEmpty);
  });

  test('shared device persistence preserves golden bytes, names and collision suffixes', () async {
    final ledger = await custodyLedger();
    final source = Wal(timerStart: 1720000000, codec: BleAudioCodec.opus, seconds: 1, device: 'device');
    final frames = [
      [0, 128, 255],
      [4, 5]
    ];
    var seq = 0;
    final first = await ledger.persistDeviceChunk(
        source: source,
        frames: frames,
        timerStart: source.timerStart,
        admittedGeneration: ledger.sessionGeneration,
        nextCollisionSequence: () => seq++);
    final second = await ledger.persistDeviceChunk(
        source: source,
        frames: frames,
        timerStart: source.timerStart,
        admittedGeneration: ledger.sessionGeneration,
        nextCollisionSequence: () => seq++);
    expect(first.filePath, source.getFileName());
    expect(second.filePath, (source.getFileName() as String).replaceFirst('.bin', '_u0.bin'));
    const golden = [3, 0, 0, 0, 0, 128, 255, 2, 0, 0, 0, 4, 5];
    expect(await File('${dir.path}/${first.filePath}').readAsBytes(), golden);
    expect(await File('${dir.path}/${second.filePath}').readAsBytes(), golden);
    final flash = await ledger.persistDeviceChunk(
        source: source,
        frames: frames,
        timerStart: source.timerStart,
        admittedGeneration: ledger.sessionGeneration,
        nextCollisionSequence: () => seq++,
        originalStorage: WalStorage.flashPage,
        fileName: () => 'audio_limitless_opus_16000_1_fs320_r123_0_1720000000000.bin');
    expect(await File('${dir.path}/${flash.filePath}').readAsBytes(), golden);
    expect(await ledger.hasDurableWal(flash, admittedGeneration: ledger.sessionGeneration), isTrue);
  });
}
