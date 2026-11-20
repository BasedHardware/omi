import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_response_schema.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/capture/local_stt_custody.dart';
import 'package:omi/services/wals/device_capture_clock.dart';
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
    dir = await Directory.systemTemp.createTemp('orphan-recovery-');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (_) async => dir.path);
    await WalFileManager.init();
    await json('wals.json', {
      'wals': [row('existing.bin')..['on_device_only'] = true]
    });
  });
  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), null);
    await dir.delete(recursive: true);
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
