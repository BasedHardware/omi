import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
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
  late List<bool> claims;
  late LocalWalSyncImpl sync;

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();

    tempDir = await Directory.systemTemp.createTemp('sync_manifest_claim_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    await WalFileManager.init();

    claims = [];
    SyncRateLimiter.instance.clear();
    sync = LocalWalSyncImpl(
      _Listener(),
      uploadGate: SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        uploader: (files, {onUploadProgress, conversationId, claimLiveCapture = false, geolocation}) async {
          claims.add(claimLiveCapture);
          return UploadFilesResult.queued('job-${claims.length}');
        },
        fairUseStatusLoader: () async => {'stage': 'none'},
      ),
    );
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    SyncRateLimiter.instance.clear();
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  Future<Wal> writeWal(int timerStart, {String? conversationId}) async {
    final name = 'audio_$timerStart.bin';
    await File('${tempDir.path}/$name').writeAsBytes(List<int>.filled(64, 1));
    return Wal(
      timerStart: timerStart,
      codec: BleAudioCodec.opus,
      seconds: 60,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      device: 'omi',
      filePath: name,
      conversationId: conversationId,
    );
  }

  test('a conversation split across batches never claims a manifest for a remainder', () async {
    // The capture manifest is immutable per conversation. Seven WALs drain as
    // 5 + 2; the first batch cannot claim it, and the second must not either —
    // a claim covering only the remainder splits one conversation's audio
    // across both server meters and spends the claim on a subset.
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    sync.testWals = [for (var index = 0; index < 7; index++) await writeWal(now - index, conversationId: 'c1')];

    await sync.syncAll();

    expect(claims.length, 2);
    expect(claims, everyElement(isFalse));
  });

  test('a conversation that fits one batch still claims', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    sync.testWals = [for (var index = 0; index < 3; index++) await writeWal(now - index, conversationId: 'c1')];

    await sync.syncAll();

    expect(claims, [true]);
  });
}
