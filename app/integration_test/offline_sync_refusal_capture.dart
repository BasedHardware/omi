// Native acceptance target: production sync provider/owner/UI, synthetic upload boundary.
// Run only on a dedicated simulator: --flavor dev -t integration_test/offline_sync_refusal_capture.dart.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _Syncs {
  _Syncs(this.phone);
  final LocalWalSyncImpl phone;
  bool get isStorageSyncing => false;
  bool get isSdCardSyncing => false;
  Future<List<Wal>> getAllWals() => phone.getAllWals();
  Future<void> refreshWalsFromDevice({String? firmwareVersion}) async {}
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) => phone.syncAll(progress: progress);
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) =>
      phone.syncWal(wal: wal, progress: progress);
  FlashSyncStallReason get flashStallReason => FlashSyncStallReason.none;
}

class _Service implements IWalService {
  _Service(this.syncs);
  final _Syncs syncs;
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

class _Device extends ChangeNotifier implements DeviceProvider {
  @override
  String get currentFirmwareVersion => 'Unknown';
  @override
  Future<void> refreshRingStorageStatus() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

Future<void> main() async {
  MarionetteBinding.ensureInitialized();
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();
  Env.overrideApiBaseUrl('http://127.0.0.1:18949/');
  await WalFileManager.init();
  final directory = await getApplicationDocumentsDirectory();
  final index = File('${directory.path}/sync-refusal-fixture.json');
  final requests = <List<String>>[];
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
      requests.add(files.map((file) => file.uri.pathSegments.last).toList());
      await File('${directory.path}/sync-refusal-requests.json').writeAsString(jsonEncode(requests));
      if (files.length > 1 || files.single.path.contains('future')) {
        throw const SyncUploadHttpException(400, 'Audio file could not be processed by server');
      }
      return UploadFilesResult.done(SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []));
    },
  );
  final sync = LocalWalSyncImpl(
    _Listener(),
    uploadGate: gate,
    persistWals: (wals) => index.writeAsString(jsonEncode(wals.map((wal) => wal.toJson()).toList())).then((_) {}),
  );
  final wals = <Wal>[];
  final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
  for (var i = 0; i < 3; i++) {
    final start = now - 600 + i * 60;
    final name = 'audio_sync_refusal_fixture_${i == 2 ? 'future' : 'valid'}_$start.bin';
    // Valid framed 16 kHz PCM silence, so the existing Share Recording path can decode it.
    final bytes = Uint8List(324 * 6000);
    final view = ByteData.sublistView(bytes);
    for (var offset = 0; offset < bytes.length; offset += 324) {
      view.setUint32(offset, 320, Endian.little);
    }
    await File('${directory.path}/$name').writeAsBytes(bytes);
    wals.add(Wal(
      timerStart: start,
      codec: BleAudioCodec.pcm16,
      seconds: 60,
      status: WalStatus.uploadRejected,
      storage: WalStorage.disk,
      device: 'phone',
      filePath: name,
    ));
  }
  sync.testWals = wals;
  final provider = SyncProvider(
    walService: _Service(_Syncs(sync)),
    uploadGate: gate,
    startBackgroundSync: false,
  );
  await provider.initialized;
  OmiColors.active = OmiColors.forBrightness(Brightness.dark);
  runApp(MultiProvider(
    providers: [
      ChangeNotifierProvider<SyncProvider>.value(value: provider),
      ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
      ChangeNotifierProvider<DeviceProvider>(create: (_) => _Device()),
    ],
    child: MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: buildOmiTheme(brightness: Brightness.dark),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: const AutoSyncPage(),
    ),
  ));
}
