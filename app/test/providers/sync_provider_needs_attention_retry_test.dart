import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

/// The Offline Sync card counted "N recordings need attention" and offered a
/// Sync button that ran the automatic drain — which skips every one of those
/// recordings by design. A user with a recording whose retry budget was spent
/// pressed Sync and nothing happened, with no other way to move it.

class _Listener implements IWalSyncListener {
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}

  @override
  void onWalUpdated() {}
}

class _LocalSyncs {
  _LocalSyncs(this.phone);

  final LocalWalSyncImpl phone;

  Future<List<Wal>> getAllWals() => phone.getAllWals();

  Future<dynamic> syncAll({IWalSyncProgressListener? progress}) => phone.syncAll(progress: progress);

  Future<dynamic> syncWal({required Wal wal, IWalSyncProgressListener? progress}) =>
      phone.syncWal(wal: wal, progress: progress);

  FlashSyncStallReason get flashStallReason => FlashSyncStallReason.none;
}

class _WalService implements IWalService {
  _WalService(this.syncs);

  final _LocalSyncs syncs;

  @override
  dynamic getSyncs() => syncs;

  @override
  void start() {}

  @override
  Future<void> stop() async {}

  @override
  void subscribe(IWalServiceListener subscription, Object context) {}

  @override
  void unsubscribe(Object context) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  late List<List<String>> uploads;
  Object? uploadFailure;
  late SyncUploadGate gate;
  late LocalWalSyncImpl localSync;
  SyncProvider? provider;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();

    tempDir = await Directory.systemTemp.createTemp('needs_attention_retry_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    await WalFileManager.init();

    uploads = [];
    uploadFailure = null;
    gate = SyncUploadGate(
      limiter: SyncRateLimiter.instance,
      uploader: (files,
          {onUploadProgress,
          conversationId,
          captureEvidence,
          recordingSessionId,
          audioStartSeconds,
          audioEndSeconds,
          claimLiveCapture = false,
          geolocation}) async {
        uploads.add([for (final file in files) file.uri.pathSegments.last]);
        if (uploadFailure != null) throw uploadFailure!;
        return UploadFilesResult.queued('job-${uploads.length}');
      },
      fairUseStatusLoader: () async => {'stage': 'none'},
    );
    localSync = LocalWalSyncImpl(_Listener(), uploadGate: gate);
  });

  tearDown(() async {
    provider?.dispose();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    SyncRateLimiter.instance.clear();
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  Future<Wal> diskWal(String name, {required int timerStart}) async {
    await File('${tempDir.path}/$name').writeAsBytes(List<int>.filled(64, 1));
    return Wal(
      timerStart: timerStart,
      codec: BleAudioCodec.opus,
      seconds: 60,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      device: 'omi',
      filePath: name,
    );
  }

  Future<SyncProvider> start(List<Wal> wals) async {
    localSync.testWals = wals;
    final syncProvider = SyncProvider(
      walService: _WalService(_LocalSyncs(localSync)),
      uploadGate: gate,
      startBackgroundSync: false,
    );
    provider = syncProvider;
    await syncProvider.initialized;
    return syncProvider;
  }

  test('the Needs Attention retry uploads a recording whose automatic budget is spent', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final spent = (await diskWal('audio_spent.bin', timerStart: now - 600))
      ..retryCount = walMaxAutoRetries
      ..lastRetryAt = now - 60;
    final syncProvider = await start([spent]);

    expect(syncProvider.needsAttentionWalsCount, 1);
    expect(syncProvider.retryableAttentionWals, [spent]);

    // What the card's Sync used to do: the automatic drain skips it.
    await syncProvider.syncWals();
    expect(uploads, isEmpty);
    expect(spent.syncDisplayState, WalSyncDisplayState.failed);

    await syncProvider.retryNeedsAttentionWals();

    // Same re-arm as resetExhaustedAutoRetries: both retry fields cleared.
    expect(spent.lastRetryAt, 0);
    expect(uploads, [
      ['audio_spent.bin'],
    ]);
    expect(spent.status, WalStatus.uploaded);
    expect(syncProvider.retryableAttentionWals, isEmpty);
  });

  test('terminal recordings need attention but are never offered as retryable', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final tooOld = (await diskWal('audio_too_old.bin', timerStart: now - 600))..markOutsideRecoveryWindow();
    final syncProvider = await start([tooOld]);

    expect(syncProvider.needsAttentionWalsCount, 1);
    expect(syncProvider.retryableAttentionWals, isEmpty);

    await syncProvider.retryNeedsAttentionWals();

    expect(uploads, isEmpty);
    expect(tooOld.status, WalStatus.outsideRecoveryWindow);
  });

  test('an explicit retry recovers a persisted upload refusal without touching permanent audio verdicts', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final rejected = (await diskWal('audio_refused.bin', timerStart: now - 600))..markUploadRejected();
    final restored = Wal.fromJson(rejected.toJson());
    final tooOld = (await diskWal('audio_expired.bin', timerStart: now - 900))..markOutsideRecoveryWindow();
    final localOnly = (await diskWal('audio_private.bin', timerStart: now - 1200))
      ..markUploadRejected()
      ..onDeviceOnly = true;
    final unsupported = (await diskWal('audio_unsupported.bin', timerStart: now - 1500))..markUnsupportedAudio();
    final syncProvider = await start([restored, tooOld, localOnly, unsupported]);

    await syncProvider.syncWals();
    expect(uploads, isEmpty, reason: 'automatic wakes must not re-arm historical refusals');
    expect(syncProvider.retryableAttentionWals, [restored]);
    await syncProvider.retryNeedsAttentionWals();

    expect(uploads, [
      ['audio_refused.bin']
    ]);
    expect(restored.status, WalStatus.uploaded);
    expect(restored.timerStart, rejected.timerStart);
    expect(tooOld.status, WalStatus.outsideRecoveryWindow);
    expect(localOnly.status, WalStatus.uploadRejected);
    expect(unsupported.status, WalStatus.unsupportedAudio);
    expect(File('${tempDir.path}/audio_refused.bin').existsSync(), isTrue);
  });

  test('the error card retry re-arms the upload refusal it reports', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final wal = await diskWal('audio_card_retry.bin', timerStart: now - 600);
    final syncProvider = await start([wal]);
    uploadFailure = const SyncUploadHttpException(400, 'request refused');
    await syncProvider.syncWals();
    expect(wal.status, WalStatus.uploadRejected);
    expect(syncProvider.syncState.hasError, isTrue);

    uploadFailure = null;
    await syncProvider.retrySync();

    expect(uploads, [
      ['audio_card_retry.bin'],
      ['audio_card_retry.bin']
    ]);
    expect(wal.status, WalStatus.uploaded);
    expect(File('${tempDir.path}/audio_card_retry.bin').existsSync(), isTrue);
  });

  test('the error card retry never re-sends a too-large refusal', () async {
    // The failed sync the banner reports is the 413 itself: the bytes cannot
    // shrink, so the banner's Retry must skip it and leave the row's Delete
    // as the only way out.
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final wal = await diskWal('audio_card_too_large.bin', timerStart: now - 600);
    final syncProvider = await start([wal]);
    uploadFailure = const SyncUploadHttpException(413, 'Audio file is too large to upload');
    await syncProvider.syncWal(wal);
    expect(wal.status, WalStatus.uploadRejected);
    expect(wal.uploadRejectionReason, WalUploadRejection.tooLarge);
    expect(syncProvider.syncState.hasError, isTrue, reason: 'fixture: this row is the reported failed sync');
    expect(syncProvider.failedWal?.id, wal.id);

    uploadFailure = null;
    await syncProvider.retrySync();

    expect(uploads, hasLength(1), reason: 'a retry cannot change the bytes');
    expect(wal.status, WalStatus.uploadRejected);
  });

  test('a too-large refusal needs attention but is never re-offered by the retry-all', () async {
    // 413 is deterministic: the same bytes are the same size, so the card's
    // retry-all must skip it and leave it to the row's Delete.
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final tooLarge = (await diskWal('audio_too_large.bin', timerStart: now - 600))
      ..markUploadRejected(reasonCode: WalUploadRejection.tooLarge);
    final invalidDate = (await diskWal('audio_bad_date.bin', timerStart: now - 900))
      ..markUploadRejected(reasonCode: WalUploadRejection.invalidCaptureTime);
    final syncProvider = await start([tooLarge, invalidDate]);

    expect(syncProvider.needsAttentionWalsCount, 2);
    expect(syncProvider.retryableAttentionWals, [invalidDate]);

    await syncProvider.retryNeedsAttentionWals();

    expect(uploads, [
      ['audio_bad_date.bin']
    ]);
    expect(tooLarge.status, WalStatus.uploadRejected, reason: 'a retry cannot change the bytes');
  });
}
