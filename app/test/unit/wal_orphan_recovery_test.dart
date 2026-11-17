import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/recording_inventory.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_evidence_runs.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
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
    dir = await Directory.systemTemp.createTemp('orphan-recovery-');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (_) async => dir.path);
    await WalFileManager.init();
    await json('wals.json', {
      'wals': [row('existing.bin')]
    });
  });
  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), null);
    await dir.delete(recursive: true);
  });

  test('classifies every class, strict frames and the inclusive 28-day boundary without writes', () async {
    final files = [
      name(now - 28 * 86400),
      name(now - 28 * 86400 - 1),
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
    expect(result.orphans.where((f) => f.classification == 'recoverable').length, 2);
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
      'live_ranges': [
        {
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

  test('classifier scales to 3000 files', () async {
    await Future.wait(List.generate(3000, (i) => audio(name(now - i))));
    final result = await census();
    expect(result.orphans.length, 3000);
    expect(result.orphans.every((f) => f.classification == 'recoverable'), isTrue);
  });
  Future<LocalWalSyncImpl> ledger(
      {DateTime Function()? clock,
      Future<RecordingOrphanCensus> Function()? scan,
      Future<bool> Function()? off,
      bool foreground = true,
      Future<void> Function(List<Wal>)? persist,
      List<Map<String, Object?>>? events}) async {
    final sync = LocalWalSyncImpl(_Listener(),
        now: clock ?? () => DateTime.fromMillisecondsSinceEpoch(now * 1000),
        orphanCensus: scan ?? census,
        orphanRecoveryOff: off ?? () async => false,
        orphanForeground: () => foreground,
        orphanTelemetry: (v) => events?.add(v),
        persistWals: persist ??
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

  test('adoption is batched, oldest first, capped, durable, idempotent and never changes audio', () async {
    for (var i = 0; i < 205; i++) {
      await audio(name(now - i));
    }
    var saves = 0;
    final sync = await ledger(persist: (rows) async {
      saves++;
      await WalFileManager.saveWals(rows);
    });
    saves = 0;
    final bytes = await File('${dir.path}/${name(now - 204)}').readAsBytes();
    await sync.recoverOrphanAudio();
    expect(saves, 1);
    final adopted = sync.testWals.where((w) => w.status == WalStatus.miss).toList();
    expect(adopted.length, 200);
    expect(adopted.first.timerStart, now - 204);
    expect(adopted.last.timerStart, now - 5);
    expect(adopted.every((w) => w.ownerUid == 'owner-a' && w.totalFrames == 50 && w.seconds == 1), isTrue);
    expect(await File('${dir.path}/${name(now - 204)}').readAsBytes(), bytes);
    await sync.recoverOrphanAudio();
    expect(sync.testWals.where((w) => w.status == WalStatus.miss).length, 205);
    final before = saves;
    await sync.recoverOrphanAudio();
    expect(saves, before);
    expect((await WalFileManager.loadIndexedWals()).length, 206);
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
