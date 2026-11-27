import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_response_schema.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/live_wal_receipt.dart';
import 'package:omi/services/wals/deleted_account_uids.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/capture/local_stt_custody.dart';
import 'package:omi/services/wals/device_capture_clock.dart';
import 'package:omi/services/wals/recording_inventory.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_evidence_runs.dart';
import 'package:omi/services/wals/wal_frame_encoder.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

class _RecoveryTimer implements Timer {
  _RecoveryTimer(this.callback);
  final void Function(Timer) callback;
  @override
  bool isActive = true;
  @override
  int tick = 0;
  void fire() {
    tick++;
    callback(this);
  }

  @override
  void cancel() {
    isActive = false;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory dir;
  const now = 1794873600;
  String name(int seconds, [String device = 'pendant']) => 'audio_${device}_opus_fs320_16000_1_fs320_$seconds.bin';
  Map<String, Object?> row(String file, [String? owner = 'owner-a']) => {
        'file_path': file,
        'timer_start': now,
        'codec': 'opus_fs320',
        'storage': 'disk',
        'status': 'synced',
        'owner_uid': owner,
        'seconds': 1,
        'total_frames': 50,
      };
  Future<void> json(String name, Object value) => File('${dir.path}/$name').writeAsString(jsonEncode(value));
  Future<File> audio(String name, {List<int>? bytes}) => File('${dir.path}/$name')
      .writeAsBytes(bytes ?? List.generate(50, (_) => [1, 0, 0, 0, 7]).expand((v) => v).toList());
  Future<RecordingOrphanCensus> census() => captureRecordingCensus(
      documents: dir.path, memoryBuckets: {'active': []}, phoneSeconds: now, currentOwner: 'owner-a');
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'owner-a'});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
    LiveWalReceipt.syncDirectoryForTesting = (_) async {};
    dir = await Directory.systemTemp.createTemp('orphan-recovery-');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (_) async => dir.path);
    await WalFileManager.init();
    await json('wals.json', {
      'wals': [row('existing.bin')..['on_device_only'] = true]
    });
  });
  tearDown(() async {
    LiveWalReceipt.syncDirectoryForTesting = null;
    LiveWalReceipt.writeReceiptForTesting = null;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), null);
    await dir.delete(recursive: true);
  });

  test('the census backs off to every two hours while live audio streams, and still runs', () {
    final t0 = DateTime.utc(2026, 11, 21, 5);
    expect(orphanRecoveryDue(now: t0), isTrue, reason: 'never run: due');
    final idleLater = t0.add(const Duration(minutes: 15));
    expect(orphanRecoveryDue(now: idleLater, lastRun: t0), isTrue, reason: 'idle: every 15 minutes');
    expect(
        orphanRecoveryDue(now: idleLater, lastRun: t0, lastLiveFrame: idleLater.subtract(const Duration(seconds: 5))),
        isFalse,
        reason: 'streaming: not each quarter hour');
    expect(
        orphanRecoveryDue(now: idleLater, lastRun: t0, lastLiveFrame: idleLater.subtract(const Duration(minutes: 2))),
        isTrue,
        reason: 'a capture that stopped a while ago is idle');
    final twoHours = t0.add(orphanRecoveryStreamingInterval);
    expect(orphanRecoveryDue(now: twoHours, lastRun: t0, lastLiveFrame: twoHours), isTrue,
        reason: 'it still runs while streaming, every two hours');
  });

  test('classifies every class, strict frames and the inclusive recovery-window boundary without writes', () async {
    final files = [
      name(now - orphanRecoveryWindowSeconds),
      name(now - orphanRecoveryWindowSeconds - 1),
      // Admissible under the 60-day server lookback; the 28-day window used to expire it.
      name(now - 40 * 86400),
      name(now),
      '${name(now)}.part',
      '${name(now)}.torn',
      name(now, 'omibatchphone'),
      name(now, 'omimobilebatch'),
      'audio_bad.bin',
      name(now - 1)
    ];
    for (final f in files) {
      await audio(f);
    }
    await audio(name(now - 1), bytes: [1, 0, 0, 0, 7, 4]); // valid prefix, torn tail
    final before = {for (final f in files) f: await File('${dir.path}/$f').readAsBytes()};
    final result = await census();
    expect(result.complete, isTrue);
    expect(result.orphans.where((f) => f.classification == 'working').length, 4);
    expect(result.orphans.where((f) => f.classification == 'unparseable').length, 2);
    expect(result.orphans.where((f) => f.classification == 'expired').length, 1);
    expect(result.orphans.where((f) => f.classification == 'recoverable').length, 3);
    expect(
        result.orphans.singleWhere((f) => f.filePath.endsWith(name(now - 40 * 86400))).classification, 'recoverable');
    for (final f in files) {
      expect(await File('${dir.path}/$f').readAsBytes(), before[f]);
    }
    expect(jsonEncode(result.summary), isNot(contains('owner-a')));
    expect(jsonEncode(result.summary), isNot(contains('audio_pendant')));
  });

  test('conflicting frame-size markers cannot invent a duration', () async {
    await audio('audio_device_opus_fs320_16000_1_fs160_$now.bin');
    expect((await census()).orphans.single.classification, 'unparseable');
  });

  test('foreign history, unknown rows and foreign capture journal fence ownership', () async {
    await audio(name(now));
    await json('wals_backup.json', {
      'wals': [row('old.bin', 'owner-b')]
    });
    expect((await census()).orphans.single.classification, 'owner_unknown');
    await json('wals_backup.json', {
      'wals': [row('old.bin', null)]
    });
    expect((await census()).orphans.single.classification, 'owner_unknown');
    await File('${dir.path}/wals_backup.json').delete();
    await json('capture_committed_foreign.json', []);
    expect((await census()).orphans.single.classification, 'owner_unknown');
  });

  test('unreadable census cannot produce recoverable candidates', () async {
    await audio(name(now));
    await File('${dir.path}/wals.json.corrupt-1').writeAsString('{');
    final result = await census();
    expect(result.complete, isFalse);
    expect(result.orphans.where((f) => f.classification == 'recoverable'), isEmpty);
  });

  test('every durable source reserves its audio and owner history', () async {
    final names = List.generate(8, (i) => name(now - i));
    for (final f in names) {
      await audio(f);
    }
    await json('wals.json', {
      'wals': [row(names[0])]
    });
    await json('wals_backup.json', {
      'wals': [row(names[1])]
    });
    await json('wals.json.corrupt-1', {
      'wals': [row(names[2])]
    });
    await json('wals.json.tmp', {
      'wals': [row(names[3])]
    });
    await json('${names[4]}.batch-journal', row(names[4]));
    await json('omibatch_owners.json', {names[5]: 'owner-a'});
    await Directory('${dir.path}/pendant_ring_custody').create();
    await json('pendant_ring_custody/custody_device.json', {
      'version': 1,
      'device_id': 'device',
      'ring_ranges': [],
      'live_ranges': [
        {
          'start_seq': 0,
          'end_seq': 1,
          'start_live': 0,
          'end_live': 50,
          'wals': [
            {'file': names[6], 'owner': 'owner-a', 'bytes': 250, 'frames': 50}
          ]
        }
      ]
    });
    final hash = sha256.convert(utf8.encode('owner-a'));
    await json('capture_committed_$hash.json', []);
    final result = await census();
    expect(result.complete, isTrue);
    expect(result.orphans.map((f) => f.filePath.split('/').last), [names[7]]);
    expect(result.orphans.single.classification, 'recoverable');
    expect((result.summary['orphan_classification'] as Map)['classes']['recoverable']['count'], 1);
    await json('omibatch_owners.json', {names[5]: 'owner-b'});
    expect((await census()).orphans.single.classification, 'owner_unknown');
  });

  test('an owner receipt alone never proves the phone owner', () async {
    await json('wals.json', {'wals': []});
    await json('omibatch_owners.json', {'receipt.bin': 'owner-a'});
    await audio(name(now));
    expect((await census()).orphans.single.classification, 'owner_unknown');
  });

  test('legal ownerless ring refs reserve files and leave phone ownership unproven', () async {
    await audio(name(now));
    await audio(name(now - 1));
    await Directory('${dir.path}/pendant_ring_custody').create();
    await json('pendant_ring_custody/custody_device.json', {
      'version': 1,
      'device_id': 'device',
      'live_ranges': [],
      'ring_ranges': [
        {
          'start_seq': 0,
          'end_seq': 1,
          'wals': [
            {'file': name(now), 'bytes': 250, 'frames': 50}
          ]
        }
      ]
    });
    final result = await census();
    expect(result.complete, isTrue);
    expect(result.orphans.length, 1);
    expect(result.orphans.single.classification, 'owner_unknown');
  });

  test('valid batch-session and download receipts reserve every file', () async {
    await Directory('${dir.path}/pendant_ring_custody').create();
    for (var i = 0; i < 3; i++) {
      await audio(name(now - i));
    }
    await json('pendant_ring_custody/custody_device.json', {
      'version': 1,
      'device_id': 'device',
      'live_ranges': [],
      'ring_ranges': [],
      'batch_sessions': [
        {
          'id': 's',
          'marks': [
            [0, 0, 0]
          ],
          'chunks': [
            {'file': name(now), 'owner': 'owner-a', 'bytes': 250, 'frames': 50, 'live_start': 0, 'live_end': 50}
          ]
        }
      ]
    });
    await json('pendant_ring_custody/custody_device.json.downloads.1.tmp', {
      'device': 'device',
      'ring': 1,
      'ranges': [
        {
          'start_seq': 0,
          'end_seq': 1,
          'wals': [
            {
              'file': name(now - 1),
              'owner': 'owner-a',
              'bytes': 250,
              'frames': 50,
              'download_ring': 1,
              'download_start': 0,
              'download_end': 1,
              'download_device': 'device'
            }
          ]
        }
      ]
    });
    final result = await census();
    expect(result.complete, isTrue);
    expect(result.orphans.single.filePath, '${dir.path}/${name(now - 2)}');
  });

  test('classifier scales to 3000 files and caches only unchanged framing', () async {
    await Future.wait(List.generate(3000, (i) => audio(name(now - i))));
    final result = await census();
    expect(result.orphans.length, 3000);
    expect(result.orphans.every((f) => f.classification == 'recoverable'), isTrue);
    expect((result.summary['orphan_classification'] as Map)['frame_files_read'], 3000);
    final cached = await captureRecordingCensus(
        documents: dir.path,
        memoryBuckets: {'active': []},
        phoneSeconds: now,
        currentOwner: 'owner-a',
        frameCache: result.frameCache);
    expect((cached.summary['orphan_classification'] as Map)['frame_files_read'], 0);
    expect((cached.summary['orphan_classification'] as Map)['frame_cache_hits'], 3000);
    final exported = await captureRecordingInventory(
        documents: dir.path,
        memoryBuckets: {'active': []},
        phoneSeconds: now,
        currentOwner: 'owner-a',
        frameCache: cached.frameCache);
    expect((exported['orphan_classification'] as Map)['frame_files_read'], 0);
    expect((exported['orphan_classification'] as Map)['frame_cache_hits'], 3000);
    final changed = File('${dir.path}/${name(now)}');
    final stamp = (await changed.stat()).modified;
    await changed.writeAsBytes(List.filled(250, 0)); // same size, invalid framing
    await changed.setLastModified(stamp.add(const Duration(seconds: 1)));
    final rechecked = await captureRecordingCensus(
        documents: dir.path,
        memoryBuckets: {'active': []},
        phoneSeconds: now,
        currentOwner: 'owner-a',
        frameCache: cached.frameCache);
    expect((rechecked.summary['orphan_classification'] as Map)['frame_files_read'], 1);
    expect((rechecked.summary['orphan_classification'] as Map)['frame_cache_hits'], 2999);
    expect(rechecked.orphans.singleWhere((f) => f.filePath == changed.path).classification, 'unparseable');
    // An unchanged malformed file is not reread on every wake...
    final sameDay = await captureRecordingCensus(
        documents: dir.path,
        memoryBuckets: {'active': []},
        phoneSeconds: now + 3600,
        currentOwner: 'owner-a',
        frameCache: rechecked.frameCache);
    expect((sameDay.summary['orphan_classification'] as Map)['frame_files_read'], 0);
    expect((sameDay.summary['orphan_classification'] as Map)['frame_cache_hits'], 3000);
    expect(sameDay.orphans.singleWhere((f) => f.filePath == changed.path).classification, 'unparseable');
    // ...but zero may mean a transient read failure, so the negative result expires after a day.
    final retried = await captureRecordingCensus(
        documents: dir.path,
        memoryBuckets: {'active': []},
        phoneSeconds: now + 86400,
        currentOwner: 'owner-a',
        frameCache: sameDay.frameCache);
    expect((retried.summary['orphan_classification'] as Map)['frame_files_read'], 1);
    expect((retried.summary['orphan_classification'] as Map)['frame_cache_hits'], 2999);
  });
  test('unowned and out-of-window orphans are classified without reading audio', () async {
    await audio(name(now - 40 * 86400));
    await json('wals_backup.json', {
      'wals': [row('foreign.bin', 'owner-b')]
    });
    await audio(name(now - 60));
    final result = await census();
    expect((result.summary['orphan_classification'] as Map)['frame_files_read'], 0);
    expect(result.orphans.map((f) => f.classification).toSet(), {'owner_unknown'});
  });
  Future<LocalWalSyncImpl> ledger(
      {DateTime Function()? clock,
      SyncUploadGate? gate,
      Timer Function(Duration, void Function(Timer))? periodic,
      void Function(Map<String, Object?>)? onEvent,
      Future<RecordingOrphanCensus> Function()? scan,
      Future<bool> Function()? off,
      bool foreground = true,
      bool Function()? foregroundProbe,
      bool realCensus = false,
      bool realPersistence = false,
      Future<void> Function(List<Wal>)? persist,
      List<Map<String, Object?>>? events,
      Future<bool> Function()? reclaimOff,
      void Function(Map<String, Object?>)? onReclaim}) async {
    final sync = LocalWalSyncImpl(_Listener(),
        now: clock ?? () => DateTime.fromMillisecondsSinceEpoch(now * 1000),
        uploadGate: gate,
        periodic: periodic,
        orphanCensus: realCensus ? null : scan ?? census,
        orphanRecoveryOff: off ?? () async => false,
        orphanReclaimOff: reclaimOff,
        orphanReclaimTelemetry: onReclaim,
        orphanForeground: foregroundProbe ?? () => foreground, orphanTelemetry: (v) {
      events?.add(v);
      onEvent?.call(v);
    },
        deltaIndexAllowed: realPersistence ? () async => true : null,
        persistWals: realPersistence
            ? null
            : persist ??
                (rows) async {
                  await WalFileManager.saveWals(rows);
                });
    sync.start();
    await sync.walReady;
    addTearDown(() async {
      await sync.stop();
      (await sync.indexWorkerForTesting)?.close();
    });
    return sync;
  }

  final receiptFrames = List.generate(50, (i) => [i]);

  Future<void> captureReceiptAudio(LocalWalSyncImpl sync) async {
    await sync.onAudioCodecChanged(BleAudioCodec.opusFS320);
    sync.setDeviceInfo('pendant', 'Omi DevKit');
    sync.setActiveRecordingSessionId('receipt-session');
    for (final payload in receiptFrames) {
      sync.onFrameCaptured(WalFrame(payload: payload, syncKey: FrameSyncKey([payload.single, 0, 0])),
          captureRoot: 'receipt-capture');
    }
  }

  File receiptFor(String name) => File('${LiveWalReceipt.directory(dir).path}/$name.json');

  test('receipt publication syncs both rename directories before returning', () async {
    final synced = <String>[];
    LiveWalReceipt.syncDirectoryForTesting = (directory) async => synced.add(directory.path);
    final id = LiveWalReceipt.newId();
    final filename = LiveWalReceipt.uniqueName(name(now), id);
    final audioFile = File('${dir.path}/$filename');
    final captured = Wal(
      codec: BleAudioCodec.opusFS320,
      timerStart: now,
      seconds: 1,
      totalFrames: receiptFrames.length,
      storage: WalStorage.mem,
      status: WalStatus.miss,
      ownerUid: 'owner-a',
      device: 'pendant',
    );
    await LiveWalReceipt.prepare(audioFile, captured, id, encodeWalFrames(receiptFrames));
    expect(synced, [
      dir.path,
      LiveWalReceipt.directory(dir).path,
      dir.path,
      LiveWalReceipt.directory(dir).path,
      '${LiveWalReceipt.directory(dir).path}/staging',
      LiveWalReceipt.directory(dir).path,
    ]);
    expect(await audioFile.exists(), isFalse);
    expect(await receiptFor(filename).exists(), isTrue);
  });

  test('post-rename directory sync failure retires the unpublished receipt', () async {
    final receiptDirectory = LiveWalReceipt.directory(dir);
    var receiptDirectorySyncs = 0;
    LiveWalReceipt.syncDirectoryForTesting = (directory) async {
      if (directory.path == receiptDirectory.path && ++receiptDirectorySyncs == 3) {
        throw const FileSystemException('injected post-rename directory sync failure');
      }
    };
    final id = LiveWalReceipt.newId();
    final filename = LiveWalReceipt.uniqueName(name(now), id);
    final audioFile = File('${dir.path}/$filename');
    final captured = Wal(
      codec: BleAudioCodec.opusFS320,
      timerStart: now,
      seconds: 1,
      totalFrames: receiptFrames.length,
      storage: WalStorage.mem,
      status: WalStatus.miss,
      ownerUid: 'owner-a',
      device: 'pendant',
    );

    await expectLater(
      LiveWalReceipt.prepare(audioFile, captured, id, encodeWalFrames(receiptFrames)),
      throwsA(isA<FileSystemException>()),
    );

    expect(receiptDirectorySyncs, 4, reason: 'the failed publication gets a durable cleanup attempt');
    expect(await receiptFor(filename).exists(), isFalse);
    expect(await audioFile.exists(), isFalse);
    expect(receiptDirectory.listSync().whereType<File>(), isEmpty);
  });

  test('partial staging receipt write is removed and its directory synced', () async {
    final synced = <String>[];
    LiveWalReceipt.syncDirectoryForTesting = (directory) async => synced.add(directory.path);
    LiveWalReceipt.writeReceiptForTesting = (file, body) async {
      await file.writeAsString(body.substring(0, 12), flush: true);
      throw const FileSystemException('injected partial receipt write');
    };
    final id = LiveWalReceipt.newId();
    final filename = LiveWalReceipt.uniqueName(name(now), id);
    final staging = Directory('${LiveWalReceipt.directory(dir).path}/staging');
    final captured = Wal(
      codec: BleAudioCodec.opusFS320,
      timerStart: now,
      seconds: 1,
      totalFrames: receiptFrames.length,
      storage: WalStorage.mem,
      status: WalStatus.miss,
      ownerUid: 'owner-a',
      device: 'pendant',
    );

    await expectLater(
      LiveWalReceipt.prepare(File('${dir.path}/$filename'), captured, id, encodeWalFrames(receiptFrames)),
      throwsA(isA<FileSystemException>()),
    );

    expect(staging.listSync(), isEmpty);
    expect(synced, contains(staging.path));
    expect(receiptFor(filename).existsSync(), isFalse);
  });

  test('receipt publication calls the durability channel with each exact directory', () async {
    LiveWalReceipt.syncDirectoryForTesting = null;
    final calls = <MethodCall>[];
    const channel = MethodChannel('com.omi/live_wal_receipt_durability');
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls.add(call);
      return null;
    });
    addTearDown(() => messenger.setMockMethodCallHandler(channel, (_) async => null));
    final id = LiveWalReceipt.newId();
    final filename = LiveWalReceipt.uniqueName(name(now), id);
    final captured = Wal(
      codec: BleAudioCodec.opusFS320,
      timerStart: now,
      seconds: 1,
      totalFrames: receiptFrames.length,
      storage: WalStorage.mem,
      status: WalStatus.miss,
      ownerUid: 'owner-a',
      device: 'pendant',
    );

    await LiveWalReceipt.prepare(File('${dir.path}/$filename'), captured, id, encodeWalFrames(receiptFrames));

    expect(calls, isNotEmpty);
    expect(calls.every((call) => call.method == 'syncDirectory'), isTrue);
    final paths = calls.map((call) => (call.arguments as Map)['path']).toSet();
    expect(paths, contains(dir.path));
    expect(paths, contains(LiveWalReceipt.directory(dir).path));
    expect(paths, contains('${LiveWalReceipt.directory(dir).path}/staging'));
  });

  test('receipt-directory durability failure persists an owner-stamped audio fallback', () async {
    LiveWalReceipt.syncDirectoryForTesting = null;
    const channel = MethodChannel('com.omi/live_wal_receipt_durability');
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(
      channel,
      (call) async {
        final directory = (call.arguments as Map)['path'];
        if (directory == LiveWalReceipt.directory(dir).path) {
          throw PlatformException(code: 'injected_receipt_directory_sync_failure');
        }
        return null;
      },
    );
    addTearDown(() => messenger.setMockMethodCallHandler(channel, (_) async => null));
    final writer = await ledger(realCensus: true);
    await captureReceiptAudio(writer);

    await writer.finalizeCurrentSession();

    final written = writer.testWals.singleWhere((wal) => wal.recordingSessionId == 'receipt-session');
    expect(written.storage, WalStorage.disk);
    expect(written.ownerUid, 'owner-a');
    expect(written.liveFileWriteId, isNull);
    final audioFile = File('${dir.path}/${written.filePath}');
    expect(await audioFile.readAsBytes(), orderedEquals(encodeWalFrames(receiptFrames)));
    final indexed = await WalFileManager.loadIndexedWals();
    expect(indexed.singleWhere((wal) => wal.filePath == written.filePath).ownerUid, 'owner-a');
    expect(await receiptFor(written.filePath!).exists(), isFalse);
    expect(LiveWalReceipt.directory(dir).listSync().whereType<File>(), isEmpty);
  }, skip: LiveWalReceipt.writeEnabled ? false : 'Receipt writer is disabled by dart-define');

  test('audio directory durability failure leaves bytes in memory and on disk', () async {
    LiveWalReceipt.syncDirectoryForTesting = (_) async {
      throw const FileSystemException('injected directory sync failure');
    };
    final writer = await ledger(realCensus: true);
    await captureReceiptAudio(writer);
    await writer.finalizeCurrentSession();
    final pending = writer.testWals.singleWhere((wal) => wal.recordingSessionId == 'receipt-session');
    expect(pending.storage, WalStorage.mem);
    final files = dir.listSync().whereType<File>().where((file) => file.path.endsWith('.bin')).toList();
    expect(files, hasLength(1));
    expect(await files.single.readAsBytes(), orderedEquals(encodeWalFrames(receiptFrames)));
    expect(LiveWalReceipt.directory(dir).listSync().whereType<File>(), isEmpty);
  }, skip: LiveWalReceipt.writeEnabled ? false : 'Receipt writer is disabled by dart-define');

  for (final scenario in ['witness', 'no witness', 'new account']) {
    final hasOwnerWitness = scenario == 'witness';
    test('real interrupted first index write survives restart ($scenario)', () async {
      await json('wals.json', {
        'wals': [if (hasOwnerWitness) row('existing.bin')],
      });
      var failWrite = false;
      final writer = await ledger(
          realCensus: true,
          persist: (rows) async {
            if (failWrite) throw const FileSystemException('injected index failure');
            expect(await WalFileManager.saveWals(rows), isTrue);
          });
      await captureReceiptAudio(writer);

      failWrite = true;
      try {
        await expectLater(writer.finalizeCurrentSession(), throwsA(isA<FileSystemException>()));
      } finally {
        failWrite = false;
      }
      final files = dir.listSync().whereType<File>().where((f) => f.path.endsWith('.bin')).toList();
      expect(files, hasLength(1));
      expect(await files.single.readAsBytes(), orderedEquals(encodeWalFrames(receiptFrames)));
      final fileName = files.single.uri.pathSegments.last;
      expect(await receiptFor(fileName).exists(), isTrue);
      expect(await WalFileManager.loadIndexedWals(), isNot(contains(predicate<Wal>((w) => w.filePath == fileName))));

      if (scenario == 'new account') {
        SharedPreferencesUtil().uid = 'owner-b';
        await audio(name(now, 'other-device'));
        await json('wals.json', {
          'wals': [row(name(now, 'other-device'), 'owner-b')],
        });
      }

      // New ledger only sees durable state, simulating process loss before retry.
      final restarted = await ledger(realCensus: true);
      await restarted.recoverOrphanAudio();
      if (scenario == 'new account') {
        expect(restarted.testWals.where((w) => w.filePath == fileName), isEmpty);
        expect(restarted.testForeignWals.singleWhere((w) => w.filePath == fileName).ownerUid, 'owner-a');
        SharedPreferencesUtil().uid = 'owner-a';
        await restarted.rehydrateForCurrentUser();
      }
      final recovered = restarted.testWals.singleWhere((w) => w.filePath == fileName);
      expect(recovered.ownerUid, 'owner-a');
      expect(recovered.holdForUser, isTrue);
      expect(recovered.totalFrames, receiptFrames.length);
      expect(recovered.recordingSessionId, 'receipt-session');
      expect(recovered.captureRoot, 'receipt-capture');
      expect(recovered.sourceFrameStart, 0);
      expect(recovered.liveRingId, isNull);
      expect(recovered.syncedAt, 0);
      expect(await restarted.hasDurableWal(recovered, admittedGeneration: restarted.sessionGeneration), isTrue);
      expect(await files.single.readAsBytes(), orderedEquals(encodeWalFrames(receiptFrames)));
    });
  }

  test('exact receipt keeps the original local policy without restoring release authority', () async {
    final id = LiveWalReceipt.newId();
    final filename = LiveWalReceipt.uniqueName(name(now), id);
    final file = File('${dir.path}/$filename');
    final bytes = encodeWalFrames(receiptFrames);
    final captured = Wal(
      codec: BleAudioCodec.opusFS320,
      timerStart: now,
      seconds: 1,
      totalFrames: receiptFrames.length,
      storage: WalStorage.mem,
      status: WalStatus.miss,
      ownerUid: 'owner-a',
      device: 'pendant',
      onDeviceOnly: true,
      capturedOnDeviceOnly: true,
      liveRingId: 3,
      liveOrdinalStart: 0,
      liveOrdinalEnd: receiptFrames.length,
      liveDeviceId: 'pendant',
    )..liveConnectionEpoch = 2;
    await LiveWalReceipt.prepare(file, captured, id, bytes);
    await file.writeAsBytes(bytes, flush: true);

    final restarted = await ledger(realCensus: true);
    final replayed = restarted.testWals.singleWhere((w) => w.filePath == filename);
    expect(replayed.ownerUid, 'owner-a');
    expect(replayed.onDeviceOnly, isTrue);
    expect(replayed.capturedOnDeviceOnly, isTrue);
    expect(replayed.holdForUser, isTrue);
    expect(replayed.liveRingId, isNull);
    expect(replayed.liveOrdinalStart, isNull);
    expect(replayed.liveOrdinalEnd, isNull);
    expect(replayed.liveConnectionEpoch, isNull);
    expect(replayed.liveDeviceId, isNull);
    expect(replayed.syncedAt, 0);
    expect(isAutoUploadEligible(replayed), isFalse);
    expect(await restarted.hasDurableWal(replayed, admittedGeneration: restarted.sessionGeneration), isTrue);
  });

  Future<File> makePendingReceipt(String? owner, {List<int>? audioBytes}) async {
    final id = LiveWalReceipt.newId();
    final basename = LiveWalReceipt.uniqueName(name(now), id);
    final file = File('${dir.path}/$basename');
    final bytes = encodeWalFrames(receiptFrames);
    final captured = Wal(
      codec: BleAudioCodec.opusFS320,
      timerStart: now,
      seconds: 1,
      totalFrames: receiptFrames.length,
      storage: WalStorage.mem,
      status: WalStatus.miss,
      ownerUid: owner,
      device: 'pendant',
    );
    await LiveWalReceipt.prepare(file, captured, id, bytes);
    return file.writeAsBytes(audioBytes ?? bytes, flush: true);
  }

  test('stale receipt replay does not emit index unavailable telemetry', () async {
    final audioFile = await makePendingReceipt('owner-a');
    final basename = audioFile.uri.pathSegments.last;
    final persistStarted = Completer<void>();
    final releasePersist = Completer<void>();
    final events = <WalWriteReceipt>[];
    var failReplaySave = true;
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => DateTime.fromMillisecondsSinceEpoch(now * 1000),
        liveWalReceiptTelemetry: events.add,
        persistWals: (rows) async {
          if (rows.any((wal) => wal.filePath == basename)) {
            if (failReplaySave) {
              if (!persistStarted.isCompleted) persistStarted.complete();
              await releasePersist.future;
              failReplaySave = false;
              throw const FileSystemException('injected stale index save failure');
            }
          }
          expect(await WalFileManager.saveWals(rows), isTrue);
        });
    sync.start();
    addTearDown(() async {
      if (!releasePersist.isCompleted) releasePersist.complete();
      await sync.stop();
      (await sync.indexWorkerForTesting)?.close();
    });
    await persistStarted.future.timeout(const Duration(seconds: 5));
    sync.clearUserData();
    releasePersist.complete();
    await sync.walReady;
    expect(events.where((event) => event.result == WalWriteReceiptResult.indexUnavailable), isEmpty);
    expect(await audioFile.exists(), isTrue);
  });

  Future<void> purgeOwnerA({
    required bool coldStart,
    LocalWalSyncImpl? existing,
    bool rejectForeignReplay = false,
  }) async {
    if (coldStart) {
      SharedPreferencesUtil().uid = 'owner-b';
      expect(await saveDeletedAccountUids(['owner-a']), isTrue);
      final restarted = await ledger(
        realCensus: true,
        persist: rejectForeignReplay
            ? (rows) async {
                // Exercise the purge check while this valid foreign file is
                // still unindexed. Successful replay would reserve its path.
                if (rows.any((wal) => wal.ownerUid == 'owner-c')) {
                  throw const FileSystemException('injected foreign replay save failure');
                }
                expect(await WalFileManager.saveWals(rows), isTrue);
              }
            : null,
      );
      expect(restarted.testWals.where((w) => w.ownerUid == 'owner-a'), isEmpty);
    } else {
      await existing!.purgeAccountWals('owner-a');
    }
  }

  for (final coldStart in [false, true]) {
    test('account purge removes its exact pending audio (cold start $coldStart)', () async {
      final existing = coldStart ? null : await ledger(realCensus: true);
      final deletedCopy = await makePendingReceipt('owner-a');
      final receipt = receiptFor(deletedCopy.uri.pathSegments.last);
      final indexed = await WalFileManager.loadIndexedWals();
      expect(indexed.map((wal) => wal.filePath), isNot(contains(deletedCopy.uri.pathSegments.last)));

      await purgeOwnerA(coldStart: coldStart, existing: existing);

      const purgeOff = bool.fromEnvironment('OMI_LIVE_WAL_RECEIPT_PURGE_OFF');
      expect(await deletedCopy.exists(), purgeOff);
      expect(await receipt.exists(), purgeOff);
    });

    for (final scenario in [
      'foreign owner',
      'unknown owner',
      'digest mismatch',
      'outside path',
      'symlink outside documents',
      'backup reference',
      'quarantined index reference',
      'unreadable quarantined index',
    ]) {
      test('account purge keeps pending audio with $scenario (cold start $coldStart)', () async {
        final existing = coldStart ? null : await ledger(realCensus: true);
        final owner = switch (scenario) {
          'foreign owner' => 'owner-c',
          'unknown owner' => null,
          _ => 'owner-a',
        };
        final bytes = scenario == 'digest mismatch'
            ? encodeWalFrames(List.generate(50, (_) => [255]))
            : encodeWalFrames(receiptFrames);
        final retained = await makePendingReceipt(owner, audioBytes: bytes);
        final basename = retained.uri.pathSegments.last;
        final receipt = receiptFor(basename);
        if (scenario == 'outside path' || scenario == 'symlink outside documents') {
          final outside = await dir.parent.createTemp('orphan-purge-outside-');
          addTearDown(() => outside.delete(recursive: true));
          final otherFile = await retained.copy('${outside.path}/$basename');
          if (scenario == 'outside path') {
            final body = jsonDecode(await receipt.readAsString()) as Map<String, dynamic>;
            body['wal']['file_path'] = otherFile.path;
            await receipt.writeAsString(jsonEncode(body));
          } else {
            await retained.delete();
            await Link(retained.path).create(otherFile.path);
          }
          addTearDown(() async => expect(await otherFile.readAsBytes(), orderedEquals(bytes)));
        }
        if (scenario == 'backup reference') {
          await json('wals_backup.json', {
            'wals': [row(basename, 'owner-c')],
          });
        }
        final quarantined = scenario == 'quarantined index reference' || scenario == 'unreadable quarantined index';
        if (quarantined) {
          if (scenario == 'quarantined index reference') {
            await json('wals.json', {
              'wals': [row(basename, 'owner-c')..['timer_start'] = 'invalid'],
            });
          } else {
            await File('${dir.path}/wals.json').writeAsString('{');
          }
          if (!coldStart) await WalFileManager.loadIndexedWals();
        }

        await purgeOwnerA(coldStart: coldStart, existing: existing, rejectForeignReplay: scenario == 'foreign owner');

        if (quarantined) {
          expect(dir.listSync().where((file) => file.path.startsWith('${dir.path}/wals.json.corrupt-')), isNotEmpty);
        }
        expect(await retained.readAsBytes(), orderedEquals(bytes));
        expect(await receipt.exists(), isTrue);
      });
    }
  }

  for (final replaceAudio in [false, true]) {
    test('account purge requires exact bytes after a failed live index save (replaced $replaceAudio)', () async {
      var failWrite = false;
      final writer = await ledger(
          realCensus: true,
          persist: (rows) async {
            if (failWrite) throw const FileSystemException('injected index failure');
            expect(await WalFileManager.saveWals(rows), isTrue);
          });
      await captureReceiptAudio(writer);
      failWrite = true;
      try {
        await expectLater(writer.finalizeCurrentSession(), throwsA(isA<FileSystemException>()));
      } finally {
        failWrite = false;
      }
      final pending = writer.testWals.singleWhere((wal) => wal.liveFileWriteId != null);
      final basename = pending.filePath!;
      final file = File('${dir.path}/$basename');
      expect((await WalFileManager.loadIndexedWals()).map((wal) => wal.filePath), isNot(contains(basename)));
      if (replaceAudio) {
        await file.writeAsBytes(encodeWalFrames(List.generate(50, (_) => [255])), flush: true);
      }

      await writer.purgeAccountWals('owner-a');

      const purgeOff = bool.fromEnvironment('OMI_LIVE_WAL_RECEIPT_PURGE_OFF');
      expect(await file.exists(), replaceAudio || purgeOff);
      expect(await receiptFor(basename).exists(), replaceAudio || purgeOff);
    });
  }

  test('bounded quarantine reference scan allows more than the former 64 archive limit', () async {
    final audioFile = await makePendingReceipt('owner-a');
    for (var i = 0; i < 65; i++) {
      await File('${dir.path}/wals.json.corrupt-$i').writeAsString('{"wals":[]}');
    }

    final result = await WalFileManager.purgeUnindexedLiveWalReceipts(
      owners: {'owner-a'},
      reservedNames: {},
      mayDelete: (_) => true,
    );

    expect(result.referenceScanIncomplete, isFalse);
    expect(result.removed, 1);
    expect(await audioFile.exists(), isFalse);
  });

  test('bounded index reference scan covers large Documents directories', () async {
    final audioFile = await makePendingReceipt('owner-a');
    await Future.wait(List.generate(4100, (i) => File('${dir.path}/unrelated-$i').create()));

    final result = await WalFileManager.purgeUnindexedLiveWalReceipts(
      owners: {'owner-a'},
      reservedNames: {},
      mayDelete: (_) => true,
    );

    expect(result.removed, 1);
    expect(result.referenceScanIncomplete, isFalse);
    expect(await audioFile.exists(), isFalse);
  });

  test('bounded reference scan accepts the maximum receipt census alongside other sources', () async {
    final ringDirectory = Directory('${dir.path}/pendant_ring_custody')..createSync();
    for (var i = 0; i < 511; i++) {
      await File('${ringDirectory.path}/receipt-$i.json').writeAsString('{}');
    }
    for (var i = 0; i < LiveWalReceipt.maxInventorySourceEntries; i++) {
      await makePendingReceipt('owner-a');
    }

    final result = await census();

    expect(result.sourcesUnchanged(), isTrue,
        reason: '512 other metadata sources plus the 128-entry receipt budget fit the 640-source fence');
  });

  test('receipt scan excludes staging and retired directories from its entry budget', () async {
    await Directory('${LiveWalReceipt.directory(dir).path}/staging').create(recursive: true);
    await Directory('${LiveWalReceipt.directory(dir).path}/retired').create(recursive: true);
    for (var i = 0; i < 127; i++) {
      await makePendingReceipt('owner-a');
    }

    final result = await census();

    expect(result.complete, isTrue);
    expect(result.summary['orphan_census_complete'], isTrue);
    expect(result.summary['receipt_scan_truncated'], isFalse);
  });

  test('unexpected receipt-directory entries do not fence unrelated census results', () async {
    final basename = LiveWalReceipt.uniqueName(name(now - 2), LiveWalReceipt.newId());
    final managedAudio = await audio(basename);
    final receiptDirectory = LiveWalReceipt.directory(dir);
    await Directory('${receiptDirectory.path}/unexpected-directory').create(recursive: true);
    await File('${receiptDirectory.path}/notes.txt').writeAsString('not a receipt');

    final result = await census();
    final managedOrphan = result.orphans.singleWhere((file) => file.filePath == managedAudio.path);

    expect(result.complete, isTrue);
    expect(result.summary['receipt_scan_errors'], 2);
    expect(result.summary['symlinks_skipped'], 0);
    expect(managedOrphan.classification, 'receiptless_managed');
    expect(managedOrphan.reclaimSkipReason(DateTime.fromMillisecondsSinceEpoch(now * 1000)), 'managed_receipt_missing');
  });

  test('receipt budget truncation preserves census and withholds managed recovery authority', () async {
    for (var i = 0; i < 129; i++) {
      await makePendingReceipt('owner-a');
    }

    final result = await census();
    final receiptless = result.orphans.where((file) => file.classification == 'receiptless_managed');

    expect(result.complete, isTrue);
    expect(result.summary['receipt_scan_truncated'], isTrue);
    expect(receiptless, isNotEmpty);
    expect(
      receiptless.every((file) =>
          file.reclaimSkipReason(DateTime.fromMillisecondsSinceEpoch(now * 1000)) == 'managed_receipt_missing'),
      isTrue,
    );
  });

  test('over-budget quarantine reference scan retains audio and reports incomplete evidence', () async {
    final audioFile = await makePendingReceipt('owner-a');
    await Future.wait(
        List.generate(4097, (i) => File('${dir.path}/wals.json.corrupt-$i').writeAsString('{"wals":[]}')));

    final result = await WalFileManager.purgeUnindexedLiveWalReceipts(
      owners: {'owner-a'},
      reservedNames: {},
      mayDelete: (_) => true,
    );

    expect(result.referenceScanIncomplete, isTrue);
    expect(result.removed, 0);
    expect(await audioFile.exists(), isTrue);
  });

  test('over-byte-budget quarantine reference scan fails closed without reading it', () async {
    final audioFile = await makePendingReceipt('owner-a');
    final oversizedIndex = File('${dir.path}/wals.json.corrupt-oversized');
    await oversizedIndex.writeAsString('{"wals":[]}');
    final handle = await oversizedIndex.open(mode: FileMode.append);
    await handle.truncate(128 * 1024 * 1024 + 1);
    await handle.close();

    final result = await WalFileManager.purgeUnindexedLiveWalReceipts(
      owners: {'owner-a'},
      reservedNames: {},
      mayDelete: (_) => true,
    );

    expect(result.referenceScanIncomplete, isTrue);
    expect(result.removed, 0);
    expect(await audioFile.exists(), isTrue);
  });

  test('stale purge snapshots refresh under the index writer lock', () async {
    final audioFile = await makePendingReceipt('owner-a');
    final basename = audioFile.uri.pathSegments.last;
    final receiptBody = jsonDecode(await receiptFor(basename).readAsString()) as Map<String, dynamic>;
    final wal = Wal.fromJson(receiptBody['wal'] as Map<String, dynamic>);
    final snapshot = (await WalFileManager.captureLiveWalPurgeSnapshot())!;
    final capturedRevision = snapshot.revision;
    expect(await WalFileManager.saveWals(await WalFileManager.loadIndexedWals()), isTrue);
    expect(WalFileManager.indexRevision, greaterThan(capturedRevision));

    expect(await WalFileManager.matchesPendingLiveWalPurge(audioFile, wal, snapshot), isTrue);
    expect(snapshot.revision, WalFileManager.indexRevision);
  });

  test('stale purge snapshot denies deletion when the basename gains an index reference', () async {
    final audioFile = await makePendingReceipt('owner-a');
    final basename = audioFile.uri.pathSegments.last;
    final receiptBody = jsonDecode(await receiptFor(basename).readAsString()) as Map<String, dynamic>;
    final wal = Wal.fromJson(receiptBody['wal'] as Map<String, dynamic>);
    final snapshot = (await WalFileManager.captureLiveWalPurgeSnapshot())!;
    final indexed = await WalFileManager.loadIndexedWals();
    expect(await WalFileManager.saveWals([...indexed, wal]), isTrue);

    expect(await WalFileManager.matchesPendingLiveWalPurge(audioFile, wal, snapshot), isFalse);
    expect(await audioFile.exists(), isTrue);
    expect(await receiptFor(basename).exists(), isTrue);
  });

  test('account purge retains managed audio when its reference snapshot is incomplete', () async {
    final writer = await ledger(realCensus: true);
    final audioFile = await makePendingReceipt('owner-a');
    final basename = audioFile.uri.pathSegments.last;
    final receiptBody = jsonDecode(await receiptFor(basename).readAsString()) as Map<String, dynamic>;
    final wal = Wal.fromJson(receiptBody['wal'] as Map<String, dynamic>);
    writer.testWals.add(wal);
    await File('${dir.path}/wals.json.corrupt-unreadable').writeAsString('{');

    await writer.purgeAccountWals('owner-a');

    expect(writer.testWals, contains(wal));
    expect(await audioFile.exists(), isTrue);
    expect(await receiptFor(basename).exists(), isTrue);
  });

  test('receiptless managed audio is visible but cannot be recovered or reclaimed', () async {
    final basename = LiveWalReceipt.uniqueName(name(now - 2), LiveWalReceipt.newId());
    final candidate = await audio(basename);
    final result = await census();
    final orphan = result.orphans.singleWhere((file) => file.filePath == candidate.path);
    expect(orphan.classification, 'receiptless_managed');
    expect(orphan.reclaimSkipReason(DateTime.fromMillisecondsSinceEpoch(now * 1000)), 'managed_receipt_missing');
    expect(result.summary['orphan_census_complete'], isTrue);
    expect(orphan.info, isNull);
  });

  test('receipt-managed basename keeps both backend timestamp contracts and estimated run identity', () {
    final id = List.filled(32, 'a').join();
    const original = 'audio_pendant_opus_fs320_16000_1_fs320_clkeoriginal_1795272480.125.bin';
    final managed = LiveWalReceipt.uniqueName(original, id);
    final tokens = managed.split('_');
    expect(tokens.take(7), ['audio', 'pendant', 'opus', '16000', '1', 'fs320', '1795272480.125']);
    expect(tokens[tokens.length - 2], 'clkeoriginal');
    expect(tokens.last, '1795272480.125.bin');
    expect(LiveWalReceipt.isManagedBasename(managed), isTrue);
    expect(LiveWalReceipt.isManagedBasename(original), isFalse);
  });

  for (final indexFails in [false, true]) {
    test('receipt custody distinguishes publication and index failures ($indexFails)', () async {
      final directory = LiveWalReceipt.directory(dir);
      if (!indexFails) await File(directory.path).writeAsString('cannot create receipt directory');
      var failWrite = false;
      var persistCalls = 0;
      final writer = await ledger(
          realCensus: true,
          persist: (rows) async {
            persistCalls++;
            if (failWrite) throw const FileSystemException('injected index failure');
            expect(await WalFileManager.saveWals(rows), isTrue);
          });
      await captureReceiptAudio(writer);
      failWrite = indexFails;
      if (indexFails) {
        await expectLater(writer.finalizeCurrentSession(), throwsA(isA<FileSystemException>()));
      } else {
        await writer.finalizeCurrentSession();
      }
      failWrite = false;
      final written = writer.testWals.singleWhere((w) => w.recordingSessionId == 'receipt-session');
      if (indexFails) {
        expect(persistCalls, greaterThan(0));
        expect(written.storage, WalStorage.disk);
        expect(written.liveFileWriteId, isNotNull);
        expect(await File('${dir.path}/${written.filePath}').exists(), isTrue);
        expect(await receiptFor(written.filePath!).exists(), isTrue);
        expect((await WalFileManager.loadIndexedWals()).map((wal) => wal.filePath), isNot(contains(written.filePath)));
      } else {
        expect(persistCalls, greaterThan(0));
        expect(written.storage, WalStorage.disk);
        expect(written.liveFileWriteId, isNull);
        final audioFile = File('${dir.path}/${written.filePath}');
        expect(await audioFile.readAsBytes(), orderedEquals(encodeWalFrames(receiptFrames)));
        expect(await receiptFor(written.filePath!).exists(), isFalse);
        expect((await WalFileManager.loadIndexedWals()).singleWhere((wal) => wal.filePath == written.filePath).ownerUid,
            'owner-a');

        final restarted = await ledger(realCensus: true);
        final replayed = restarted.testWals.singleWhere((wal) => wal.filePath == written.filePath);
        expect(replayed.ownerUid, 'owner-a');
        expect(replayed.liveFileWriteId, isNull);
      }
    });
  }

  test('receipt issuance kill switch still replays and retires existing receipts', () async {
    final id = LiveWalReceipt.newId();
    final filename = LiveWalReceipt.uniqueName(name(now - 10), id);
    final file = File('${dir.path}/$filename');
    final bytes = encodeWalFrames(receiptFrames);
    final captured = Wal(
      codec: BleAudioCodec.opusFS320,
      timerStart: now - 10,
      seconds: 1,
      totalFrames: receiptFrames.length,
      storage: WalStorage.mem,
      status: WalStatus.miss,
      ownerUid: 'owner-a',
      device: 'pendant',
    );
    await LiveWalReceipt.prepare(file, captured, id, bytes);
    await file.writeAsBytes(bytes, flush: true);

    final writer = await ledger(realCensus: true, realPersistence: true);
    expect(writer.testWals.singleWhere((w) => w.filePath == filename).liveFileWriteId, id);
    await captureReceiptAudio(writer);
    await writer.finalizeCurrentSession();
    final newlyWritten = writer.testWals.singleWhere((w) => w.recordingSessionId == 'receipt-session');
    expect(newlyWritten.liveFileWriteId, isNull);
    expect(LiveWalReceipt.isManagedBasename(newlyWritten.filePath!), isFalse);
    expect(await receiptFor(filename).exists(), isTrue);

    await ledger(realCensus: true);
    expect(await receiptFor(filename).exists(), isFalse);
    expect(await file.readAsBytes(), orderedEquals(bytes));
  }, skip: LiveWalReceipt.writeEnabled ? 'Run with --dart-define=OMI_LIVE_WAL_RECEIPT_OFF=true' : false);

  for (final delta in [false, true]) {
    test('retire only after both restart indexes cover the transaction (delta $delta)', () async {
      final writer = await ledger(realCensus: true, realPersistence: delta);
      await captureReceiptAudio(writer);
      await writer.finalizeCurrentSession();
      final written = writer.testWals.singleWhere((w) => w.liveFileWriteId != null);
      final fileName = written.filePath!;
      expect(await receiptFor(fileName).exists(), isTrue);

      final beforeCleanup = await ledger(realCensus: true);
      final reopen = beforeCleanup.testWals.where((w) => w.filePath == fileName).toList();
      expect(reopen, hasLength(1), reason: 'a committed main row supersedes receipt replay');
      expect(reopen.single.holdForUser, written.holdForUser);
      expect(await receiptFor(fileName).exists(), isTrue);

      final extraName = name(now - 5, 'different-device');
      await audio(extraName);
      await writer.addExternalWal(Wal.fromJson(row(extraName)), admittedGeneration: writer.sessionGeneration);
      expect(await receiptFor(fileName).exists(), isTrue, reason: 'index writes alone do not retire cover');
      final confirmed = await ledger(realCensus: true);
      expect(confirmed.testWals.singleWhere((w) => w.filePath == fileName).ownerUid, 'owner-a');
      expect(await receiptFor(fileName).exists(), isFalse);

      await File('${dir.path}/wals.json').writeAsString('{', flush: true);
      final restarted = await ledger(realCensus: true);
      final recovered = restarted.testWals.singleWhere((w) => w.filePath == fileName);
      expect(recovered.ownerUid, 'owner-a');
      expect(recovered.liveFileWriteId, written.liveFileWriteId);
      expect(await File('${dir.path}/$fileName').readAsBytes(), orderedEquals(encodeWalFrames(receiptFrames)));
    });
  }

  test('an unreadable backup row with matching identity cannot retire the receipt', () async {
    final writer = await ledger(realCensus: true, realPersistence: true);
    await captureReceiptAudio(writer);
    await writer.finalizeCurrentSession();
    final original = writer.testWals.singleWhere((w) => w.liveFileWriteId != null);
    final fileName = original.filePath!;
    await json('wals.json', {
      'wals': [original.toJson()..['total_frames'] = 'invalid'],
    });

    final extraName = name(now - 5, 'different-device');
    await audio(extraName);
    await writer.addExternalWal(Wal.fromJson(row(extraName)), admittedGeneration: writer.sessionGeneration);
    await ledger(realCensus: true);
    expect(await receiptFor(fileName).exists(), isTrue);

    await File('${dir.path}/wals.json').delete();
    final restarted = await ledger(realCensus: true);
    final replayed = restarted.testWals.singleWhere((w) => w.filePath == fileName);
    expect(replayed.ownerUid, 'owner-a');
    expect(replayed.liveFileWriteId, original.liveFileWriteId);
    expect(replayed.totalFrames, receiptFrames.length);
    expect(replayed.holdForUser, isTrue);
  });

  test('a replaced or missing file cannot replay a stale receipt or be heuristically adopted', () async {
    final writer = await ledger(realCensus: true);
    await captureReceiptAudio(writer);
    await writer.finalizeCurrentSession();
    final written = writer.testWals.singleWhere((w) => w.liveFileWriteId != null);
    final nameOfFile = written.filePath!;
    final file = File('${dir.path}/$nameOfFile');
    await json('wals.json', {
      'wals': [row('existing.bin')],
    });
    await file.delete();

    final afterDelete = await ledger(realCensus: true);
    expect(afterDelete.testWals.where((w) => w.filePath == nameOfFile), isEmpty);
    expect(await receiptFor(nameOfFile).exists(), isTrue);
    await file.writeAsBytes(encodeWalFrames(List.generate(50, (_) => [255])), flush: true);

    final afterReuse = await ledger(realCensus: true);
    expect(afterReuse.testWals.where((w) => w.filePath == nameOfFile), isEmpty);
    expect((await census()).orphans.where((file) => file.filePath.endsWith(nameOfFile)), isEmpty);
  });

  test('deleting a shared row disarms its pending receipt while leaving the other file reference intact', () async {
    final writer = await ledger(realCensus: true);
    await captureReceiptAudio(writer);
    await writer.finalizeCurrentSession();
    final original = writer.testWals.singleWhere((w) => w.liveFileWriteId != null);
    final fileName = original.filePath!;
    final companion = Wal.fromJson(original.toJson()
      ..['device'] = 'other'
      ..remove('live_file_write_id'));
    writer.testWals = [original, companion];
    await writer.deleteWal(original);

    final file = File('${dir.path}/$fileName');
    expect(await file.exists(), isTrue);
    expect(await receiptFor(fileName).exists(), isFalse);
    expect(writer.testWals, [companion]);

    await json('wals.json', {'wals': []});
    final restarted = await ledger(realCensus: true);
    expect(restarted.testWals, isEmpty);
    expect((await census()).orphans.where((entry) => entry.filePath == file.path), isEmpty);
  });

  test('staging residue does not consume the pending replay budget', () async {
    final directory = await LiveWalReceipt.directory(dir).create();
    final staging = await Directory('${directory.path}/staging').create();
    for (var i = 0; i < 130; i++) {
      final tempName = LiveWalReceipt.uniqueName(name(now - 100 - i), LiveWalReceipt.newId());
      await File('${staging.path}/$tempName.json').writeAsString('{');
    }
    final writer = await ledger(realCensus: true);
    await captureReceiptAudio(writer);
    await writer.finalizeCurrentSession();
    final written = writer.testWals.singleWhere((w) => w.liveFileWriteId != null);
    await json('wals.json', {'wals': []});

    final restarted = await ledger(realCensus: true);
    final replayed = restarted.testWals.singleWhere((w) => w.filePath == written.filePath);
    expect(replayed.liveFileWriteId, written.liveFileWriteId);
    expect(replayed.ownerUid, 'owner-a');
  });

  test('later startup replays past receipts the previous batch indexed', () async {
    final bytes = encodeWalFrames(receiptFrames);
    for (var i = 0; i < 129; i++) {
      final id = LiveWalReceipt.newId();
      final timestamp = now - i;
      final filename = LiveWalReceipt.uniqueName(name(timestamp), id);
      final file = File('${dir.path}/$filename');
      final captured = Wal(
        codec: BleAudioCodec.opusFS320,
        timerStart: timestamp,
        seconds: 1,
        totalFrames: receiptFrames.length,
        storage: WalStorage.mem,
        status: WalStatus.miss,
        ownerUid: 'owner-a',
        device: 'pendant',
      );
      await LiveWalReceipt.prepare(file, captured, id, bytes);
      await file.writeAsBytes(bytes, flush: true);
    }

    final first = await ledger(realCensus: true);
    final initial = first.testWals.where((w) => w.liveFileWriteId != null);
    expect(initial, hasLength(128));
    final remainingAudio = dir
        .listSync()
        .whereType<File>()
        .where((f) => f.path.endsWith('.bin'))
        .singleWhere((file) => initial.every((w) => w.filePath != file.uri.pathSegments.last));
    final firstCensus = await census();
    final remainingOrphan = firstCensus.orphans.where((file) => file.filePath == remainingAudio.path);
    expect(firstCensus.complete, isTrue);
    expect(firstCensus.summary['receipt_scan_truncated'], isTrue);
    expect(remainingOrphan.length, lessThanOrEqualTo(1));
    if (remainingOrphan.isNotEmpty) {
      expect(remainingOrphan.single.classification, 'receiptless_managed');
      expect(remainingOrphan.single.reclaimSkipReason(DateTime.fromMillisecondsSinceEpoch(now * 1000)),
          'managed_receipt_missing');
    }
    expect(await remainingAudio.readAsBytes(), orderedEquals(bytes));

    final next = await ledger(realCensus: true);
    final replayed = next.testWals.where((w) => w.liveFileWriteId != null);
    expect(replayed.map((w) => w.liveFileWriteId).toSet(), hasLength(129));
    expect(replayed, hasLength(129));
  });

  test('replay progresses past a full page of invalid receipts on a later launch', () async {
    final directory = await LiveWalReceipt.directory(dir).create();
    for (var i = 0; i < 128; i++) {
      final id = i.toRadixString(16).padLeft(32, '0');
      final nameWithReceipt = LiveWalReceipt.uniqueName(name(now - 100 - i), id);
      await File('${directory.path}/$nameWithReceipt.json').writeAsString('{');
    }
    final id = 'f' * 32;
    final filename = LiveWalReceipt.uniqueName(name(now), id);
    final file = File('${dir.path}/$filename');
    final bytes = encodeWalFrames(receiptFrames);
    final captured = Wal(
      codec: BleAudioCodec.opusFS320,
      timerStart: now,
      seconds: 1,
      totalFrames: receiptFrames.length,
      storage: WalStorage.mem,
      status: WalStatus.miss,
      ownerUid: 'owner-a',
      device: 'pendant',
    );
    await LiveWalReceipt.prepare(file, captured, id, bytes);
    await file.writeAsBytes(bytes, flush: true);

    final first = await ledger(realCensus: true);
    expect(first.testWals.where((wal) => wal.filePath == filename), isEmpty);

    final next = await ledger(realCensus: true);
    expect(next.testWals.singleWhere((wal) => wal.filePath == filename).ownerUid, 'owner-a');
    expect(await file.readAsBytes(), orderedEquals(bytes));
  });

  test('an unreadable receipt still reserves its audio basename', () async {
    final directory = await LiveWalReceipt.directory(dir).create();
    final base = LiveWalReceipt.uniqueName(name(now - 2), LiveWalReceipt.newId());
    final candidate = await audio(base);
    for (var i = 0; i < 130; i++) {
      await File('${directory.path}/${name(now - 100 - i)}.json.tmp').writeAsString('{');
    }
    await receiptFor(base).writeAsString('{');
    final restarted = await ledger(realCensus: true);
    await restarted.recoverOrphanAudio();
    expect(restarted.testWals.where((w) => w.filePath == base), isEmpty);
    expect((await census()).orphans.where((file) => file.filePath == candidate.path), isEmpty);
    expect(await candidate.exists(), isTrue);
  });

  test('clean single-owner phone automatically uploads recovered miss rows', () async {
    await json('wals.json', {
      'wals': [row('existing.bin')]
    });
    await audio(name(now));
    final sync = await ledger(realCensus: true);
    await sync.recoverOrphanAudio();
    final recovered = sync.testWals.singleWhere((w) => w.status == WalStatus.miss);
    expect(recovered.holdForUser, isFalse);
    expect(recovered.onDeviceOnly, isFalse);
    expect(isAutoUploadEligible(recovered), isTrue);
    expect(Wal.fromJson(recovered.toJson()).holdForUser, isFalse);
  });

  for (final source in [
    'wals.json',
    'wals_backup.json',
    'wals.json.tmp',
    'wals.json.corrupt-1',
    'wals_backup.json.corrupt-1'
  ]) {
    for (final policy in ['on_device_only', 'hold_for_user']) {
      test('$source $policy history keeps recovered audio held', () async {
        await json('wals.json', {
          'wals': [row('existing.bin')]
        });
        final sync = await ledger(realCensus: true);
        await json(source, {
          'wals': [row('historic.bin')..[policy] = true]
        });
        await audio(name(now));
        await sync.recoverOrphanAudio();
        final recovered = sync.testWals.singleWhere((w) => w.status == WalStatus.miss);
        expect(recovered.holdForUser, isTrue);
        expect(isAutoUploadEligible(recovered), isFalse);
      });
    }
  }

  for (final bucket in ['active', 'retired', 'foreign']) {
    for (final policy in ['on_device_only', 'hold_for_user']) {
      test('$bucket $policy appearing after census prevents automatic adoption', () async {
        await json('wals.json', {
          'wals': [row('existing.bin')]
        });
        await audio(name(now));
        late LocalWalSyncImpl sync;
        sync = await ledger(scan: () async {
          final result = await census();
          final history = Wal.fromJson(row('memory-only.bin')..[policy] = true);
          switch (bucket) {
            case 'active':
              sync.testWals.add(history);
            case 'retired':
              sync.testRetiredWals.add(history);
            case 'foreign':
              sync.testForeignWals.add(history);
          }
          return result;
        });
        await sync.recoverOrphanAudio();
        expect(sync.testWals.singleWhere((w) => w.status == WalStatus.miss).holdForUser, isTrue);
      });
    }
  }

  for (final preference in [
    'autoSyncOfflineRecordings',
    'onDeviceTranscription.keepEverythingOnDevice',
    'onDeviceTranscription.saveLiveHours',
    'onDeviceOverflowActive'
  ]) {
    test('$preference local-only preference holds clean-phone recovery', () async {
      await json('wals.json', {
        'wals': [row('existing.bin')]
      });
      await SharedPreferencesUtil().saveBool(preference, preference != 'autoSyncOfflineRecordings');
      await audio(name(now));
      final sync = await ledger(realCensus: true);
      await sync.recoverOrphanAudio();
      expect(sync.testWals.singleWhere((w) => w.status == WalStatus.miss).holdForUser, isTrue);
    });
  }

  for (final config in [
    '{"provider":"onDeviceWhisper","send_raw_audio_to_omi":false}',
    '{"provider":"deepgram","send_raw_audio_to_omi":true}',
    '{"provider":"omi","send_raw_audio_to_omi":false}',
    '{"provider":"unknown"}',
    '{}',
    '{',
  ]) {
    test('durable STT choice $config holds recovery on a cold start', () async {
      await json('wals.json', {
        'wals': [row('existing.bin')]
      });
      await SharedPreferencesUtil().saveString('customSttConfig', config);
      await audio(name(now));
      final sync = await ledger(realCensus: true);
      await sync.recoverOrphanAudio();
      expect(sync.testWals.singleWhere((w) => w.status == WalStatus.miss).holdForUser, isTrue);
    });
  }

  final malformedCloudConfigs = <Map<String, Object?>>[
    for (final key in ['api_key', 'language', 'model', 'url', 'host', 'request_type', 'audio_field_name']) {key: 7},
    for (final port in <Object>['bad', 1.5, -1, 0, 65536]) {'port': port},
    {'request_type': 'future_transport'},
    {'request_type': ''},
    {'headers': true},
    {
      'headers': {'key': 7}
    },
    {
      'headers': {'': 'value'}
    },
    {'params': []},
    {
      'params': {'key': []}
    },
    {'schema': []},
    for (final key in [
      'segments_path',
      'segments_text_field',
      'segments_start_field',
      'segments_end_field',
      'segments_speaker_field',
      'segments_speaker_id_field',
      'segments_is_user_field',
      'segments_person_id_field',
      'segments_translations_field',
      'text_path'
    ])
      {
        'schema': {key: true}
      },
    for (final duration in <Object>['bad', -1, 0])
      {
        'schema': {'default_segment_duration': duration}
      },
    {
      'schema': {'future_policy': true}
    },
    {'keep_everything_on_device': true},
  ];
  for (final patch in malformedCloudConfigs) {
    test('raw STT schema $patch cannot grant cloud consent', () async {
      await json('wals.json', {
        'wals': [row('existing.bin')]
      });
      await SharedPreferencesUtil()
          .saveString('customSttConfig', jsonEncode({'provider': 'omi', 'send_raw_audio_to_omi': true, ...patch}));
      await audio(name(now));
      final sync = await ledger(realCensus: true);
      await sync.recoverOrphanAudio();
      expect(sync.testWals.singleWhere((w) => w.status == WalStatus.miss).holdForUser, isTrue);
    });
  }
  for (final config in [
    CustomSttConfig.defaultConfig.toJson(),
    CustomSttConfig.defaultConfig
        .copyWith(
            port: 9000,
            headers: {'fixture': 'value'},
            params: {'language': 'en'},
            requestType: 'multipart_form',
            schemaJson: SttResponseSchema.openAI.toJson())
        .toJson(),
  ]) {
    test('valid complete Omi STT schema $config permits cloud recovery', () async {
      await json('wals.json', {
        'wals': [row('existing.bin')]
      });
      await SharedPreferencesUtil().saveString('customSttConfig', jsonEncode(config));
      await audio(name(now));
      final sync = await ledger(realCensus: true);
      await sync.recoverOrphanAudio();
      expect(sync.testWals.singleWhere((w) => w.status == WalStatus.miss).holdForUser, isFalse);
    });
  }

  test('a kill switch settling during the budget write fences publication', () async {
    await audio(name(now));
    var reads = 0;
    final sync = await ledger(off: () async => ++reads >= 3);
    await sync.recoverOrphanAudio();
    expect(sync.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
  });

  for (final value in [
    1,
    true,
    <String>['local']
  ]) {
    test('non-string STT setting $value cannot grant cloud consent', () async {
      await json('wals.json', {
        'wals': [row('existing.bin')]
      });
      final prefs = await SharedPreferences.getInstance();
      if (value is int) await prefs.setInt('customSttConfig', value);
      if (value is bool) await prefs.setBool('customSttConfig', value);
      if (value is List<String>) await prefs.setStringList('customSttConfig', value);
      await audio(name(now));
      final sync = await ledger(realCensus: true);
      await sync.recoverOrphanAudio();
      expect(sync.testWals.singleWhere((w) => w.status == WalStatus.miss).holdForUser, isTrue);
    });
  }

  for (final key in [
    'autoSyncOfflineRecordings',
    'onDeviceTranscription.keepEverythingOnDevice',
    'onDeviceTranscription.saveLiveHours',
    'onDeviceOverflowActive',
    'customSttConfig.corrupt-1'
  ]) {
    test('unknown or quarantined consent $key stays held', () async {
      await json('wals.json', {
        'wals': [row('existing.bin')]
      });
      await (await SharedPreferences.getInstance()).setInt(key, 1);
      await audio(name(now));
      final sync = await ledger(realCensus: true);
      await sync.recoverOrphanAudio();
      expect(sync.testWals.singleWhere((w) => w.status == WalStatus.miss).holdForUser, isTrue);
    });
  }

  for (final key in [
    'localRecordingJobs',
    'localRecordingJobsCorrupt',
    'batchAudioDir',
    'flash_page_pending_uploads',
    'localRecordingJobs.corrupt-1'
  ]) {
    test('invalid custody preference $key makes adoption fail closed', () async {
      await (await SharedPreferences.getInstance()).setInt(key, 1);
      await audio(name(now));
      final sync = await ledger(realCensus: true);
      await sync.recoverOrphanAudio();
      expect(sync.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
    });
  }

  for (final payload in <Map<String, Object?>>[
    {'version': 99, 'device_id': 'device'},
    {'version': 1.0, 'device_id': 'device'},
    {
      'version': 1,
      'device_id': 'device',
      'ring_ranges': [7]
    },
    {'version': 1, 'device_id': 'device', 'live_ranges': {}},
    {
      'version': 1,
      'device_id': 'device',
      'ring_ranges': [
        {
          'start_seq': 0,
          'end_seq': 1,
          'wals': [7]
        }
      ]
    },
    {
      'version': 1,
      'device_id': 'device',
      'batch_sessions': [
        {
          'id': 's',
          'marks': [],
          'chunks': [7]
        }
      ]
    },
    {'version': 1, 'device_id': 'device', 'future_refs': []},
    {
      'device': 'device',
      'ring': 1,
      'ranges': [7]
    },
  ]) {
    test('unsupported ring checkpoint $payload is incomplete', () async {
      await Directory('${dir.path}/pendant_ring_custody').create();
      await json('pendant_ring_custody/custody_device.json', {
        if (!payload.containsKey('ranges')) ...{'live_ranges': [], 'ring_ranges': []},
        ...payload
      });
      await audio(name(now));
      expect((await census()).complete, isFalse);
      final sync = await ledger(realCensus: true);
      await sync.recoverOrphanAudio();
      expect(sync.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
    });
  }

  test('legacy references appearing during census fence admission', () async {
    await audio(name(now));
    final sync = await ledger(scan: () async {
      final result = await census();
      await (await SharedPreferences.getInstance()).setString('localRecordingJobs', jsonEncode({name(now): 'job'}));
      return result;
    });
    await sync.recoverOrphanAudio();
    expect(sync.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
  });

  test('preference changed during census is rechecked before admission', () async {
    await json('wals.json', {
      'wals': [row('existing.bin')]
    });
    await audio(name(now));
    final sync = await ledger(scan: () async {
      final result = await census();
      await SharedPreferencesUtil().saveBool('autoSyncOfflineRecordings', false);
      return result;
    });
    await sync.recoverOrphanAudio();
    expect(sync.testWals.singleWhere((w) => w.status == WalStatus.miss).holdForUser, isTrue);
  });

  for (final source in ['pending files', 'jobs', 'quarantined jobs']) {
    test('ownerless legacy $source prevents orphan adoption despite a current-owner row', () async {
      final orphan = await audio(name(now));
      await audio(name(now - 1));
      final snapshot = await captureRecordingCensus(
          documents: dir.path,
          memoryBuckets: {'active': []},
          phoneSeconds: now,
          currentOwner: 'owner-a',
          legacyFiles: source == 'pending files' ? ['${dir.path}/${name(now - 1)}'] : [],
          legacyJobs: source == 'jobs' ? jsonEncode({name(now - 1): 'old-job'}) : '',
          corruptLegacyJobs: source == 'quarantined jobs' ? jsonEncode({name(now - 1): 'old-job'}) : '');
      expect(snapshot.complete, isTrue);
      expect(snapshot.orphans.length, 1);
      expect(snapshot.orphans.single.classification, 'owner_unknown');
      final bytes = await orphan.readAsBytes();
      final sync = await ledger(scan: () async => snapshot);
      await sync.recoverOrphanAudio();
      expect(sync.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
      expect(await orphan.readAsBytes(), bytes);
    });
  }

  test('adoption is batched, oldest first, capped, durable, idempotent and never changes audio', () async {
    for (var i = 0; i < 205; i++) {
      await audio(name(now - i));
    }
    var saves = 0;
    final events = <Map<String, Object?>>[];
    final sync = await ledger(
        realCensus: true,
        events: events,
        persist: (rows) async {
          saves++;
          await WalFileManager.saveWals(rows);
        });
    saves = 0;
    final bytes = await File('${dir.path}/${name(now - 204)}').readAsBytes();
    await sync.recoverOrphanAudio();
    expect(saves, 1);
    final adopted = sync.testWals.where((w) => w.status == WalStatus.miss).toList();
    expect(adopted.length, 200);
    expect(adopted.every((w) => w.holdForUser && !w.onDeviceOnly && !isAutoUploadEligible(w)), isTrue);
    expect(Wal.fromJson(adopted.first.toJson()).holdForUser, isTrue);
    expect(adopted.first.timerStart, now - 204);
    expect(adopted.last.timerStart, now - 5);
    expect(adopted.every((w) => w.ownerUid == 'owner-a' && w.totalFrames == 50 && w.seconds == 1), isTrue);
    expect(await File('${dir.path}/${name(now - 204)}').readAsBytes(), bytes);
    final exported = await captureRecordingInventory(
        documents: dir.path,
        memoryBuckets: sync.recordingInventorySnapshot,
        phoneSeconds: now,
        currentOwner: 'owner-a',
        frameCache: sync.orphanFrameCache);
    expect((exported['orphan_classification'] as Map)['frame_files_read'], 0);
    expect((exported['orphan_classification'] as Map)['frame_cache_hits'], 5);
    expect(jsonEncode(exported), isNot(contains(dir.path)));
    await sync.recoverOrphanAudio();
    expect(sync.testWals.where((w) => w.status == WalStatus.miss).length, 205);
    expect((events.first['classification'] as Map)['frame_files_read'], 205);
    expect((events[1]['classification'] as Map)['frame_files_read'], 0);
    expect((events[1]['classification'] as Map)['frame_cache_hits'], 5);
    final before = saves;
    await sync.recoverOrphanAudio();
    expect(saves, before);
    expect((await WalFileManager.loadIndexedWals()).length, 206);
  });

  test('a durable adoption publishes the held view after a background transition', () async {
    await audio(name(now));
    var foreground = true, armed = false;
    final events = <Map<String, Object?>>[];
    final sync = await ledger(
        foregroundProbe: () => foreground,
        events: events,
        persist: (rows) async {
          await WalFileManager.saveWals(rows);
          if (armed) foreground = false;
        });
    final view = LocalRecordingsProvider(ledger: sync);
    addTearDown(view.dispose);
    await view.refresh();
    final revision = sync.heldRevision.value;
    armed = true;
    await sync.recoverOrphanAudio();
    await pumpEventQueue(times: 100);
    expect(sync.heldRevision.value, revision + 1);
    expect(view.recordings.length, 1);
    expect(events.single['result'], 'completed');
    expect((events.single['counts'] as Map)['adopted'], 1);
    expect((await WalFileManager.loadIndexedWals()).where((w) => w.status == WalStatus.miss).length, 1);
  });

  test('production delta worker rolls back failed orphan publication and retries', () async {
    final file = await audio(name(now));
    final bytes = await file.readAsBytes();
    final events = <Map<String, Object?>>[];
    final sync = await ledger(realPersistence: true, events: events);
    final tmp = await Directory('${dir.path}/wals.json.tmp').create();
    await sync.recoverOrphanAudio();
    expect(sync.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
    expect((events.last['counts'] as Map)['adopted'] ?? 0, 0);
    expect(events.last['result'], 'failed', reason: 'exercise worker failure rather than an earlier census fence');
    expect(await sync.indexWorkerForTesting, isNotNull);
    expect(await file.readAsBytes(), bytes);
    await tmp.delete();
    await sync.recoverOrphanAudio();
    expect(sync.testWals.where((w) => w.status == WalStatus.miss).length, 1);
    expect((await WalFileManager.loadIndexedWals()).where((w) => w.filePath == name(now)).length, 1);
    expect(await file.readAsBytes(), bytes);
  });

  test('selected local capture route holds otherwise clean-phone recovery', () async {
    await json('wals.json', {
      'wals': [row('existing.bin')]
    });
    await audio(name(now));
    LocalSttCustody.selectedLocalRoute = true;
    addTearDown(() => LocalSttCustody.selectedLocalRoute = false);
    final sync = await ledger(realCensus: true);
    await sync.recoverOrphanAudio();
    expect(sync.testWals.singleWhere((w) => w.status == WalStatus.miss).holdForUser, isTrue);
  });

  test('persisted ring store envelope is compatible with read-only census', () async {
    final ring = await Directory('${dir.path}/pendant_ring_custody').create();
    final checkpoint = RingCustodyCheckpoint(deviceId: 'device');
    expect(checkpoint.toJson().containsKey('version'), isFalse);
    final store = PendantCustodyStore(directoryProvider: () async => ring);
    await store.saveJson('device', checkpoint.toJson());
    final persisted = jsonDecode(await File('${ring.path}/custody_device.json').readAsString());
    expect(persisted['version'], 1);
    expect((await store.load('device'))?.deviceId, 'device');
    expect((await census()).complete, isTrue);
    final legacy = Wal.fromJson(row('legacy.bin'));
    expect(legacy.onDeviceOnly, isFalse);
    expect(legacy.holdForUser, isFalse);
  });

  test('failed index save rolls back unpublished held rows and a later pass retries them', () async {
    final file = await audio(name(now));
    final bytes = await file.readAsBytes();
    var fail = false, saves = 0;
    final events = <Map<String, Object?>>[];
    final sync = await ledger(
        events: events,
        persist: (rows) async {
          saves++;
          if (fail) throw const FileSystemException('synthetic index failure');
          await WalFileManager.saveWals(rows);
        });
    final revision = sync.heldRevision.value;
    addTearDown(() {
      fail = false;
    });
    saves = 0;
    fail = true;
    await sync.recoverOrphanAudio();
    expect(sync.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
    expect(sync.heldRevision.value, revision);
    expect(events.single['result'], 'failed');
    expect((events.single['counts'] as Map)['adopted'], 0);
    expect(saves, 1);
    expect(await file.readAsBytes(), bytes);
    fail = false;
    await sync.recoverOrphanAudio();
    expect(sync.testWals.singleWhere((w) => w.status == WalStatus.miss).holdForUser, isTrue);
    expect(sync.heldRevision.value, revision + 1);
    expect(saves, 2);
    expect(await file.readAsBytes(), bytes);
  });

  SyncUploadGate uploadGate(SyncFilesUploader uploader) => SyncUploadGate(
      limiter: SyncRateLimiter.instance, fairUseStatusLoader: () async => {'stage': 'none'}, uploader: uploader);

  test('recovered rows appear in the existing view, never auto-drain, and allow explicit upload or delete', () async {
    final uploadFile = await audio(name(now));
    final deleteFile = await audio(name(now - 1));
    final bytes = await uploadFile.readAsBytes();
    var uploads = 0;
    final sync = await ledger(gate: uploadGate((files,
        {onUploadProgress,
        conversationId,
        captureEvidence,
        recordingSessionId,
        audioStartSeconds,
        audioEndSeconds,
        claimLiveCapture = false,
        geolocation}) async {
      uploads++;
      return UploadFilesResult.queued('manual-job');
    }));
    final view = LocalRecordingsProvider(ledger: sync);
    addTearDown(view.dispose);
    await view.refresh();
    expect(view.recordings, isEmpty);
    await sync.recoverOrphanAudio();
    await pumpEventQueue(times: 100);
    expect(view.recordings.length, 2, reason: 'heldRevision publishes to an already-open recordings view');
    expect(view.recordings.every((r) => r.state == LocalRecordingState.pending), isTrue);
    final held = sync.testWals.where((w) => w.holdForUser).toList();
    expect(held.length, 2);
    expect(held.every((w) => !isAutoUploadEligible(w)), isTrue);
    expect((await WalFileManager.loadIndexedWals()).where((w) => w.holdForUser).length, 2);
    await sync.syncAll();
    await sync.syncLiveCaptureOnly();
    expect(sync.getOrphanedWals(), isEmpty);
    expect(uploads, 0);
    expect(await view.upload(view.getById(name(now))!), LocalUploadOutcome.started);
    expect(uploads, 1);
    final uploaded = sync.testWals.singleWhere((w) => w.filePath == name(now));
    expect(uploaded.status, WalStatus.uploaded);
    expect(uploaded.holdForUser, isTrue);
    expect(await uploadFile.readAsBytes(), bytes);
    await view.delete(view.getById(name(now - 1))!);
    expect(await deleteFile.exists(), isFalse, reason: 'only the explicit user delete removes audio');
    expect(view.getById(name(now - 1)), isNull);
    expect(sync.testWals.any((w) => w.filePath == name(now - 1)), isFalse);
  });

  test('a refused manual upload stays held even when its automatic refusal retry is due', () async {
    var seconds = now, uploads = 0;
    final file = await audio(name(now));
    final bytes = await file.readAsBytes();
    final sync = await ledger(
        clock: () => DateTime.fromMillisecondsSinceEpoch(seconds * 1000),
        gate: uploadGate((files,
            {onUploadProgress,
            conversationId,
            captureEvidence,
            recordingSessionId,
            audioStartSeconds,
            audioEndSeconds,
            claimLiveCapture = false,
            geolocation}) async {
          uploads++;
          if (uploads == 1) throw const SyncUploadHttpException(400, 'request refused');
          return UploadFilesResult.queued('explicit-retry');
        }));
    await sync.recoverOrphanAudio();
    final view = LocalRecordingsProvider(ledger: sync, initialize: false);
    addTearDown(view.dispose);
    await view.refresh();
    expect(await view.upload(view.getById(name(now))!), LocalUploadOutcome.failed);
    final recovered = sync.testWals.singleWhere((w) => w.filePath == name(now));
    expect(recovered.status, WalStatus.uploadRejected);
    expect(recovered.holdForUser, isTrue);
    expect(uploads, 1);
    seconds += 86400;
    expect(recovered.refusalRetryDue(seconds), isTrue);
    expect(isAutoUploadEligible(recovered, nowSeconds: seconds), isFalse);
    await sync.syncAll();
    await sync.syncLiveCaptureOnly();
    expect(uploads, 1, reason: 'a refusal cannot turn a user hold into automatic consent');
    expect(await view.upload(view.getById(name(now))!), LocalUploadOutcome.started);
    expect(uploads, 2, reason: 'a later explicit Process now action still reaches the uploader');
    expect(recovered.status, WalStatus.uploaded);
    expect(recovered.holdForUser, isTrue);
    expect(await file.readAsBytes(), bytes);
  });

  for (final reason in [WalUploadRejection.tooLarge, WalUploadRejection.tooManyParts]) {
    test('held $reason keeps the existing deterministic refusal guard', () async {
      await audio(name(now));
      var uploads = 0;
      final sync = await ledger(gate: uploadGate((files,
          {onUploadProgress,
          conversationId,
          captureEvidence,
          recordingSessionId,
          audioStartSeconds,
          audioEndSeconds,
          claimLiveCapture = false,
          geolocation}) async {
        uploads++;
        throw SyncUploadHttpException(413, 'request refused', reasonCode: reason);
      }));
      await sync.recoverOrphanAudio();
      final view = LocalRecordingsProvider(ledger: sync, initialize: false);
      addTearDown(view.dispose);
      await view.refresh();
      expect(await view.upload(view.getById(name(now))!), LocalUploadOutcome.failed);
      expect(await view.upload(view.getById(name(now))!), LocalUploadOutcome.failed);
      expect(uploads, 1);
      final held = sync.testWals.singleWhere((w) => w.filePath == name(now));
      expect(held.holdForUser, isTrue);
      expect(held.status, WalStatus.uploadRejected);
      expect(await File('${dir.path}/${name(now)}').exists(), isTrue);
    });
  }

  test('manual upload past the server lookback marks outsideRecoveryWindow and retains the held file', () async {
    var seconds = now;
    const capture = now - orphanRecoveryWindowSeconds;
    final file = await audio(name(capture));
    final bytes = await file.readAsBytes();
    var uploads = 0;
    final sync = await ledger(
        clock: () => DateTime.fromMillisecondsSinceEpoch(seconds * 1000),
        gate: uploadGate((files,
            {onUploadProgress,
            conversationId,
            captureEvidence,
            recordingSessionId,
            audioStartSeconds,
            audioEndSeconds,
            claimLiveCapture = false,
            geolocation}) async {
          uploads++;
          expect(audioStartSeconds, capture.toDouble());
          expect(seconds - capture, greaterThan(serverSyncLookbackSeconds));
          throw const SyncRecoveryWindowExceededException();
        }));
    await sync.recoverOrphanAudio();
    final recovered = sync.testWals.singleWhere((w) => w.status == WalStatus.miss);
    final view = LocalRecordingsProvider(ledger: sync, initialize: false);
    addTearDown(view.dispose);
    await view.refresh();
    expect(view.getById(name(capture)), isNotNull);
    seconds += 3 * 86400;
    expect(await view.upload(view.getById(name(capture))!), LocalUploadOutcome.failed);
    expect(uploads, 1);
    expect(recovered.status, WalStatus.outsideRecoveryWindow);
    expect(recovered.holdForUser, isTrue);
    expect(isAutoUploadEligible(recovered), isFalse);
    expect(view.getById(name(capture))!.state, LocalRecordingState.failed);
    expect(sync.testWals.contains(recovered), isTrue);
    expect(await file.readAsBytes(), bytes);
    final durable = (await WalFileManager.loadIndexedWals()).singleWhere((w) => w.filePath == name(capture));
    expect(durable.status, WalStatus.outsideRecoveryWindow);
    expect(durable.holdForUser, isTrue);
  });

  test('pressure threshold never grows beyond 720', () async {
    await json('wals.json', {
      'wals': List.generate(719, (i) => {...row('existing$i.bin'), 'status': 'miss'})
    });
    for (var i = 0; i < 5; i++) {
      await audio(name(now - i));
    }
    final sync = await ledger();
    await sync.recoverOrphanAudio();
    expect(sync.testWals.where((w) => w.status == WalStatus.miss).length, 720);
    await sync.recoverOrphanAudio();
    expect(sync.testWals.length, 720);
  });

  test('daily cap survives a fresh ledger instance', () async {
    for (var i = 0; i < 450; i++) {
      await audio(name(now - i));
    }
    final first = await ledger();
    await first.recoverOrphanAudio();
    await first.recoverOrphanAudio();
    expect(first.testWals.where((w) => w.status == WalStatus.miss).length, 400);
    await first.stop();
    final prefs = await SharedPreferences.getInstance();
    await prefs.clear();
    await prefs.setString('uid', 'owner-a');
    final second = await ledger();
    await second.recoverOrphanAudio();
    expect(second.testWals.where((w) => w.status == WalStatus.miss).length, 400);
  });

  test('a torn daily budget fails closed without publishing rows', () async {
    await audio(name(now));
    await File('${dir.path}/orphan_audio_recovery_budget.json').writeAsString('{');
    final events = <Map<String, Object?>>[];
    final sync = await ledger(events: events);
    await sync.recoverOrphanAudio();
    expect(events.single['result'], 'budget_unavailable');
    expect(sync.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
  });

  test('fractional capture filenames from the real producer classify and adopt', () async {
    final base = Wal(
        timerStart: now - 1,
        codec: BleAudioCodec.opusFS320,
        seconds: 1,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        device: 'pendant');
    final fractional = walEvidenceRunFileName(base, now - 0.5, 0, 50);
    expect(fractional, contains('.5.bin'));
    await audio(fractional);
    final classified = await census();
    expect(classified.orphans.single.classification, 'recoverable');
    final sync = await ledger();
    await sync.recoverOrphanAudio();
    final recovered = sync.testWals.singleWhere((w) => w.status == WalStatus.miss);
    expect(recovered.filePath, fractional);
    expect(recovered.timerStart, now - 1);
    expect(recovered.totalFrames, 50);
  });

  test('Limitless collision and clock-run producer filenames retain timing and clock provenance', () async {
    const run = 'a1b2c3d4e5f6';
    final source = Wal(
        timerStart: now - 2,
        codec: BleAudioCodec.opusFS320,
        seconds: 1,
        storage: WalStorage.disk,
        ownerUid: 'owner-a',
        device: 'pendant',
        clockRun: run);
    expect(source.id, 'pendant_${now - 2}');
    expect(Wal.fromJson(source.toJson()).id, source.id, reason: 'legacy row ids must stay unchanged');
    final clockName = source.getFileName() as String;
    final prefix = clockName.substring(0, clockName.lastIndexOf('_'));
    final names = [
      'audio_limitless_opus_16000_1_fs320_r1234_0_${(now - 1) * 1000}.bin',
      'audio_limitless_opus_16000_1_fs320_r1234_1_clke${run}_${now * 1000}.bin',
      clockName,
      '${deviceClockCollisionPrefix(prefix, 1)}_${now - 2}.bin',
      walCollisionName(clockName, 2, false),
    ];
    for (final file in names) {
      await audio(file);
    }
    // The server cannot preserve a run separated from time by a nonce. Keep
    // that unsupported historical shape unparseable rather than lose lineage.
    final unsupported = await audio(walCollisionName(clockName, 3, true));
    final classified = await census();
    expect(classified.orphans.where((f) => f.classification == 'recoverable').length, names.length);
    expect(classified.orphans.singleWhere((f) => f.filePath == unsupported.path).classification, 'unparseable');
    final sync = await ledger();
    await sync.recoverOrphanAudio();
    final recovered = sync.testWals.where((w) => w.status == WalStatus.miss).toList();
    expect(recovered.map((w) => w.filePath), unorderedEquals(names));
    expect(recovered.map((w) => w.id).toSet(), hasLength(names.length),
        reason: 'playback/share caches are keyed by WAL id, not just the source path');
    final restored = await WalFileManager.loadWals();
    for (final wal in recovered) {
      expect(restored.singleWhere((w) => w.filePath == wal.filePath).id, wal.id,
          reason: 'file-specific recovery identity must survive the durable index');
    }
    for (final wal in recovered) {
      expect(wal.holdForUser, isTrue);
      expect(wal.totalFrames, 50);
      expect(wal.seconds, 1);
      expect(wal.clockRun, wal.filePath!.contains('_clke') ? run : null);
      expect(
          wal.timerStart,
          wal.filePath == names[0]
              ? now - 1
              : wal.filePath == names[1]
                  ? now
                  : now - 2);
    }
    expect(await unsupported.exists(), isTrue);
  });

  test('400 reservations is a true rolling 24-hour cap across a window boundary', () async {
    for (var i = 0; i < 850; i++) {
      await audio(name(now - i));
    }
    var seconds = now;
    final sync = await ledger(clock: () => DateTime.fromMillisecondsSinceEpoch(seconds * 1000));
    await sync.recoverOrphanAudio(); // 200 at t0
    seconds += 23 * 3600;
    await sync.recoverOrphanAudio(); // 200 at t0+23h
    seconds = now + 86401;
    await sync.recoverOrphanAudio(); // t0 expired, so another 200 fits
    await sync.recoverOrphanAudio(); // t0+23h and t0+24h still spend all 400
    expect(sync.testWals.where((w) => w.status == WalStatus.miss).length, 600);
  });

  test('changed audio and newly referenced files are skipped', () async {
    final file = await audio(name(now));
    final sync = await ledger(scan: () async {
      final result = await census();
      await file.writeAsBytes([1, 0, 0, 0, 8, 9]);
      return result;
    });
    await sync.recoverOrphanAudio();
    expect(sync.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
    expect(await file.readAsBytes(), [1, 0, 0, 0, 8, 9]);
  });

  test('a new index reference during census invalidates the commit', () async {
    final file = await audio(name(now));
    final events = <Map<String, Object?>>[];
    final sync = await ledger(
        events: events,
        scan: () async {
          final result = await census();
          await json('wals.json.corrupt-new', {
            'wals': [row(name(now))]
          });
          return result;
        });
    await sync.recoverOrphanAudio();
    expect(events.single['result'], 'sources_changed');
    expect(sync.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
    expect(await file.length(), 250);
  });

  test('an in-memory row registered during census is not adopted again', () async {
    await audio(name(now));
    late LocalWalSyncImpl sync;
    final events = <Map<String, Object?>>[];
    sync = await ledger(
        events: events,
        scan: () async {
          final result = await census();
          final existing = Wal(
              timerStart: now,
              codec: result.orphans.single.info!.codec,
              seconds: 1,
              totalFrames: 50,
              storage: WalStorage.disk,
              status: WalStatus.miss,
              ownerUid: 'owner-a',
              filePath: name(now));
          // Simulate intake publication without a durable write, so the file/source
          // stamp is unchanged and only the live-reference fence can protect it.
          sync.testWals.add(existing);
          return result;
        });
    await sync.recoverOrphanAudio();
    expect(sync.testWals.where((w) => w.filePath == name(now)).length, 1);
    expect((events.single['counts'] as Map)['referenced'], 1);
  });

  test('configured non-Documents audio is classified and retained with a skip reason', () async {
    final native = await Directory.systemTemp.createTemp('orphan-native-');
    addTearDown(() => native.delete(recursive: true));
    final file = await File('${native.path}/${name(now)}').writeAsBytes([1, 0, 0, 0, 7]);
    final events = <Map<String, Object?>>[];
    final sync = await ledger(
        events: events,
        scan: () => captureRecordingCensus(
            documents: dir.path,
            memoryBuckets: {'active': []},
            phoneSeconds: now,
            currentOwner: 'owner-a',
            additionalDirectories: [native.path]));
    await sync.recoverOrphanAudio();
    expect(sync.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
    expect((events.single['counts'] as Map)['outsideDocuments'], 1);
    expect(await file.readAsBytes(), [1, 0, 0, 0, 7]);
  });

  test('outside-Documents files cannot spend the adoption budget or starve eligible files', () async {
    final native = await Directory.systemTemp.createTemp('orphan-native-');
    addTearDown(() => native.delete(recursive: true));
    await Future.wait(
        List.generate(200, (i) => File('${native.path}/${name(now - 1000 - i)}').writeAsBytes([1, 0, 0, 0, 7])));
    await audio(name(now));
    final events = <Map<String, Object?>>[];
    final sync = await ledger(
        events: events,
        scan: () => captureRecordingCensus(
            documents: dir.path,
            memoryBuckets: {'active': []},
            phoneSeconds: now,
            currentOwner: 'owner-a',
            additionalDirectories: [native.path]));
    await sync.recoverOrphanAudio();
    expect(sync.testWals.where((w) => w.status == WalStatus.miss).single.filePath, name(now));
    expect((events.single['counts'] as Map)['outsideDocuments'], 200);
    final raw = jsonDecode(await File('${dir.path}/orphan_audio_recovery_budget.json').readAsString()) as Map;
    final spent = (raw.values.single as List).fold<int>(0, (n, r) => n + (r['count'] as int));
    expect(spent, 1);
    expect((await native.list().toList()).length, 200);
  });

  test('a large metadata archive defers the bounded commit, never the outside-queue census', () async {
    await audio(name(now));
    for (var i = 0; i < 513; i++) {
      await json('wals.json.corrupt-$i', {'wals': []});
    }
    final snapshot = await census();
    expect(snapshot.complete, isTrue);
    final events = <Map<String, Object?>>[];
    final sync = await ledger(events: events, scan: () async => snapshot);
    await sync.recoverOrphanAudio();
    expect(events.single['result'], 'sources_changed');
    expect(sync.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
  });

  test('expiry while waiting for adoption is counted and retains the original', () async {
    await audio(name(now - orphanRecoveryWindowSeconds));
    var seconds = now;
    final events = <Map<String, Object?>>[];
    final sync = await ledger(
        events: events,
        clock: () => DateTime.fromMillisecondsSinceEpoch(seconds * 1000),
        scan: () async {
          final snapshot = await census();
          seconds += 86400;
          return snapshot;
        });
    await sync.recoverOrphanAudio();
    expect((events.single['counts'] as Map)['expiredSinceCensus'], 1);
    expect(sync.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
  });

  test('expiry after the budget timestamp is rechecked immediately before admission', () async {
    final file = await audio(name(now - orphanRecoveryWindowSeconds));
    final bytes = await file.readAsBytes();
    var censusComplete = false, postCensusClockReads = 0;
    final events = <Map<String, Object?>>[];
    final sync = await ledger(
        events: events,
        clock: () =>
            DateTime.fromMillisecondsSinceEpoch((now + (censusComplete && postCensusClockReads++ > 0 ? 1 : 0)) * 1000),
        scan: () async {
          final snapshot = await census();
          censusComplete = true;
          return snapshot;
        });
    await sync.recoverOrphanAudio();
    expect(sync.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
    expect((events.single['counts'] as Map)['expiredSinceCensus'], 1);
    expect(await file.readAsBytes(), bytes);
  });

  test('resume and timer wakes share one 15-minute pacing gate', () async {
    var seconds = now, scans = 0;
    var done = Completer<void>();
    final timers = <_RecoveryTimer>[];
    final sync = await ledger(
        clock: () => DateTime.fromMillisecondsSinceEpoch(seconds * 1000),
        periodic: (_, callback) {
          final timer = _RecoveryTimer(callback);
          timers.add(timer);
          return timer;
        },
        scan: () {
          scans++;
          return census();
        },
        onEvent: (_) {
          if (!done.isCompleted) done.complete();
        });
    sync.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await done.future;
    expect(scans, 1);
    timers[2].fire();
    sync.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await pumpEventQueue(times: 100);
    expect(scans, 1);
    seconds += 15 * 60;
    done = Completer<void>();
    timers[2].fire();
    await done.future;
    expect(scans, 2);
  });

  test('one foreground wake runs recovery, then reclaim after recovery settles', () async {
    final order = <String>[];
    final reclaimed = Completer<void>();
    final sync = await ledger(
        onEvent: (_) => order.add('recovery'),
        reclaimOff: () async => false,
        onReclaim: (_) {
          order.add('reclaim');
          if (!reclaimed.isCompleted) reclaimed.complete();
        });
    sync.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await reclaimed.future.timeout(const Duration(seconds: 10));
    expect(order, ['recovery', 'reclaim']);
  });

  test('incomplete census and kill switch adopt nothing', () async {
    await audio(name(now));
    final events = <Map<String, Object?>>[];
    final sync = await ledger(off: () async => true, events: events);
    await sync.recoverOrphanAudio();
    expect(events.single['result'], 'kill_switch');
    expect(sync.testWals.length, 1);
    await File('${dir.path}/wals.json.corrupt-1').writeAsString('{');
    final other = await ledger(events: events);
    await other.recoverOrphanAudio();
    expect(events.last['result'], 'incomplete_census');
    expect(other.testWals.where((w) => w.status == WalStatus.miss), isEmpty);
  });

  test('admission pending, headless and background never start a census', () async {
    var scans = 0;
    Future<RecordingOrphanCensus> scan() {
      scans++;
      return census();
    }

    final barrier = Completer<List<Wal>>();
    final pending = LocalWalSyncImpl(_Listener(),
        loadWals: () => barrier.future,
        orphanCensus: scan,
        orphanForeground: () => true,
        orphanRecoveryOff: () async => false,
        orphanTelemetry: (_) {});
    pending.start();
    await pending.recoverOrphanAudio();
    expect(scans, 0);
    barrier.complete([]);
    await pending.walReady;
    await pending.stop();
    final headless = LocalWalSyncImpl(_Listener(), orphanCensus: scan, orphanTelemetry: (_) {});
    await headless.loadForOnDeviceWorker();
    await headless.recoverOrphanAudio();
    expect(scans, 0);
    final background = await ledger(scan: scan, foreground: false);
    await background.recoverOrphanAudio();
    expect(scans, 0);
  });

  test('generation changes during census stop adoption and emit one aggregate event', () async {
    await audio(name(now));
    final entered = Completer<void>(), release = Completer<void>();
    final events = <Map<String, Object?>>[];
    final sync = await ledger(
        events: events,
        scan: () async {
          final result = await census();
          entered.complete();
          await release.future;
          return result;
        });
    final pass = sync.recoverOrphanAudio();
    await entered.future;
    sync.clearUserData();
    release.complete();
    await pass;
    expect(sync.testWals, isEmpty);
    expect(events.single['result'], 'generation_changed');
    expect(jsonEncode(events), isNot(contains('owner-a')));
    expect(await File('${dir.path}/${name(now)}').exists(), isTrue);
  });
}
