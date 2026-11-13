import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:path_provider/path_provider.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/settings/sign_out.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

/// Run only in a leased disposable simulator. Real platform preferences, path
/// provider, audio files and WAL index; no Firebase account or network access.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('upgrade and A/signed-out/B/A restore waiting audio and its queued job', (tester) async {
    await SharedPreferencesUtil.init();
    final docs = await getApplicationDocumentsDirectory();
    await WalFileManager.init();
    // Refuse to overwrite an existing inventory even in a mistaken test target.
    expect(await WalFileManager.loadWals(), isEmpty);
    SharedPreferencesUtil().uid = 'rehydrate-fixture-a';
    const name = 'audio_omibatchphone_pcm16_16000_1_fs320_1790000000.bin';
    final source = File('${docs.path}/$name');
    final pcm = Uint8List(640);
    final frame = BytesBuilder()
      ..add((ByteData(4)..setUint32(0, pcm.length, Endian.little)).buffer.asUint8List())
      ..add(pcm);
    await source.writeAsBytes(frame.takeBytes(), flush: true);
    final original = await source.readAsBytes();
    await SharedPreferencesUtil().saveString('batchAudioDir', '/old-app-container/Documents');
    await SharedPreferencesUtil().saveString('localRecordingJobs', jsonEncode({name: 'fixture-accepted-job'}));
    await File('${docs.path}/omibatch_owners.json').writeAsString(jsonEncode({name: 'rehydrate-fixture-a'}));
    await clearPreferencesForSignOut();
    expect(SharedPreferencesUtil().getString('localRecordingJobs'), contains('fixture-accepted-job'));

    Future<LocalWalSyncImpl> openLedger() async {
      final ledger = LocalWalSyncImpl(_Listener(), freeDiskBytes: () async => 4 << 30);
      await ledger.loadForOnDeviceWorker();
      return ledger;
    }

    final ledger = await openLedger();
    final view = LocalRecordingsProvider(ledger: ledger, initialize: false);
    await view.refresh();
    expect(view.recordings, isEmpty);
    SharedPreferencesUtil().uid = 'rehydrate-fixture-b';
    await view.refresh();
    expect(view.recordings, isEmpty);
    expect(await ledger.getAllWals(), isEmpty);
    expect((await WalFileManager.loadWals()).single.jobId, 'fixture-accepted-job');
    expect(SharedPreferencesUtil().getString('batchAudioDir'), docs.path);
    ledger.clearUserData();
    view.clearUserData();
    await clearPreferencesForSignOut();
    SharedPreferencesUtil().uid = 'rehydrate-fixture-a';
    await view.refresh();
    expect(view.recordings.single.state.name, 'processing');
    expect((await ledger.getAllWals()).single.holdForUser, isTrue);
    expect((await ledger.getAllWals()).single.status, WalStatus.uploaded);
    expect(await source.readAsBytes(), original);
    await view.refresh();
    expect(view.recordings, hasLength(1));
    view.dispose();
    final reopened = await openLedger();
    final reopenedView = LocalRecordingsProvider(ledger: reopened, initialize: false);
    await reopenedView.refresh();
    expect(reopenedView.recordings, hasLength(1));
    expect((await reopened.getAllWals()).single.jobId, 'fixture-accepted-job');
    expect(await source.readAsBytes(), original);
    await tester.pumpWidget(
        const MaterialApp(home: Scaffold(body: Text('Waiting recording restored; audio and queued job preserved'))));
    await tester.pumpAndSettle();
    reopenedView.dispose();
    // ignore: avoid_print
    print('WAITING_REAUTH_NATIVE platform=${Platform.operatingSystem} cold_start=pass owner_isolation=pass '
        'same_owner=pass restart=pass receipt_preserved=pass bytes=${original.length}');
  });
}
