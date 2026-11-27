import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/live_wal_receipt.dart';
import 'package:omi/services/wals/recording_inventory.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../support/recording_analytics.dart';

class _Listener implements IWalSyncListener {
  @override
  void onWalUpdated() {}
  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory dir;
  const now = 1794873600, old = now - orphanReclaimAgeSeconds - 86400;
  String name(int time, [String marker = 'pendant']) => 'audio_${marker}_opus_fs320_16000_1_fs320_$time.bin';
  Map<String, Object?> row(String file, [String owner = 'owner-b']) => {
        'file_path': file,
        'timer_start': old,
        'codec': 'opus_fs320',
        'storage': 'disk',
        'status': 'miss',
        'owner_uid': owner,
        'hold_for_user': true,
      };
  Future<void> json(String file, Object value) async {
    await File('${dir.path}/$file').writeAsString(jsonEncode(value));
  }

  Future<File> audio(String file, {int modified = old}) async {
    final f = await File('${dir.path}/$file').writeAsBytes([1, 0, 0, 0, 7]);
    await f.setLastModified(DateTime.fromMillisecondsSinceEpoch(modified * 1000));
    return f;
  }

  Future<RecordingOrphanCensus> census({Map<String, List<RecordingInventoryRow>>? buckets}) => captureRecordingCensus(
      documents: dir.path, memoryBuckets: buckets ?? {'active': []}, phoneSeconds: now, currentOwner: 'owner-a');
  Future<LocalWalSyncImpl> ledger(
      {Future<bool> Function()? off,
      Future<RecordingOrphanCensus> Function()? scan,
      void Function()? afterTombstone,
      void Function(Map<String, Object?>)? event,
      bool typedTelemetry = false,
      bool foreground = true}) async {
    final sync = LocalWalSyncImpl(_Listener(),
        now: () => DateTime.fromMillisecondsSinceEpoch(now * 1000),
        orphanReclaimOff: off ?? () async => false,
        orphanCensus: scan,
        orphanForeground: () => foreground,
        orphanReclaimAfterTombstone: afterTombstone,
        orphanReclaimTelemetry: typedTelemetry ? null : event ?? (_) {},
        orphanRecoveryOff: () async => true,
        persistWals: (rows) => WalFileManager.saveWals(rows));
    sync.start();
    await sync.walReady;
    addTearDown(() async {
      await sync.stop();
      (await sync.indexWorkerForTesting)?.close();
    });
    return sync;
  }

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'owner-a'});
    await SharedPreferencesUtil.init();
    dir = await Directory.systemTemp.createTemp('orphan-reclaim-');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (_) async => dir.path);
    await WalFileManager.init();
    await json('wals.json', {
      'wals': [row('existing.bin', 'owner-a')]
    });
  });
  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), null);
    await dir.delete(recursive: true);
  });

  test('multi-account census deletes old orphan and sidecar, emits aggregates only', () async {
    await json('wals_backup.json', {
      'wals': [row('foreign.bin')]
    });
    final file = await audio(name(old));
    final sidecar = File('${file.path}.geolocation.json');
    await sidecar.writeAsString('{}');
    final events = <Map<String, Object?>>[];
    final sync = await ledger(event: events.add);
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isFalse);
    expect(await sidecar.exists(), isFalse);
    expect(events.single['deleted_files'], 1);
    expect(events.single['deleted_bytes'], 5);
    expect(jsonEncode(events), isNot(contains('owner-a')));
    expect(jsonEncode(events), isNot(contains('audio_')));
    await sync.reclaimOrphanAudio();
    expect(events.last['deleted_files'], 0);
  });
  test('receiptless managed files are counted as reclaim skips', () async {
    final filename = LiveWalReceipt.uniqueName(name(old), LiveWalReceipt.newId());
    final file = await audio(filename);
    final skips = <Map<String, Object?>>[];
    final sync = await ledger(event: skips.add);
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
    expect((skips.single['skips'] as Map)['managed_receipt_missing'], 1);
  });
  test('reclaim emits typed receiptless custody counts and scan status', () async {
    final analytics = RecordingAnalytics();
    AnalyticsManager.resetForTesting();
    AnalyticsManager.configure(analytics.adapter);
    PackageInfo.setMockInitialValues(
        appName: 'Omi Test', packageName: 'com.omi.test', version: '1.0.543', buildNumber: '992', buildSignature: '');
    await AnalyticsManager.init();
    try {
      final filename = LiveWalReceipt.uniqueName(name(old), LiveWalReceipt.newId());
      final file = await audio(filename);
      final sync = await ledger(typedTelemetry: true);
      await sync.reclaimOrphanAudio();
      await AnalyticsManager.flushPending(force: true);

      expect(await file.exists(), isTrue);
      analytics.expectSingle('Orphan Audio Receiptless Custody', {
        'phase': 'reclaim',
        'receiptless_managed_count': 1,
        'receiptless_managed_bytes': await file.length(),
        'managed_receipt_missing_skip_count': 1,
        'receipt_scan_truncated': false,
        'census_complete': true,
      });
    } finally {
      AnalyticsManager.resetForTesting();
    }
  });
  for (final source in [
    'wals.json',
    'wals_backup.json',
    'wals.json.tmp',
    'wals_backup.json.tmp',
    'wals.json.corrupt-1',
    'wals_backup.json.corrupt-1',
    'file.batch-journal',
    'omibatch_owners.json',
    'localRecordingJobs',
    'localRecordingJobsCorrupt',
    'flash_page_pending_uploads',
    'ring'
  ]) {
    test('reference in $source protects held foreign audio', () async {
      final file = await audio(name(old));
      final sync = await ledger();
      final basename = name(old);
      if (source == 'file.batch-journal') {
        await json(source, row(basename));
      } else if (source == 'omibatch_owners.json') {
        await json(source, {basename: 'owner-b'});
      } else if (source == 'ring') {
        await Directory('${dir.path}/pendant_ring_custody').create();
        await json('pendant_ring_custody/test.downloads.1.json', {
          'device': 'device',
          'ring': 1,
          'ranges': [
            {
              'start_seq': 0,
              'end_seq': 1,
              'wals': [
                {'file': basename, 'bytes': 5, 'frames': 1, 'owner': 'owner-b'}
              ]
            }
          ]
        });
        expect((await census()).complete, isTrue);
      } else if (source == 'flash_page_pending_uploads') {
        await (await SharedPreferences.getInstance()).setStringList(source, [basename]);
      } else if (source.startsWith('localRecording')) {
        await (await SharedPreferences.getInstance()).setString(source, jsonEncode({basename: 'job'}));
      } else {
        await json(source, {
          'wals': [row(basename)]
        });
      }
      await sync.reclaimOrphanAudio();
      expect(await file.exists(), isTrue);
    });
  }
  for (final bucket in ['active', 'retired', 'foreign']) {
    test('$bucket memory reference protects audio', () async {
      final file = await audio(name(old));
      final sync = await ledger(
          scan: () => census(buckets: {
                'active': [],
                bucket: [
                  RecordingInventoryRow(
                      status: 'miss',
                      captureSeconds: old,
                      audioSeconds: 1,
                      indexBytes: 5,
                      disk: true,
                      filePath: name(old),
                      owner: 'owner-b',
                      holdForUser: true)
                ]
              }));
      await sync.reclaimOrphanAudio();
      expect(await file.exists(), isTrue);
    });
  }
  test('reclaim age stays strictly beyond automatic recovery and the server lookback plus margin', () {
    // Reclaim must never delete audio the phone would still auto-recover or the server would
    // still admit. retention_contract.json margin_days is 7.
    expect(orphanReclaimMarginSeconds, greaterThanOrEqualTo(7 * 86400));
    expect(orphanRecoveryWindowSeconds, lessThan(serverSyncLookbackSeconds));
    expect(orphanReclaimAgeSeconds, greaterThan(orphanRecoveryWindowSeconds + orphanReclaimMarginSeconds));
    expect(orphanReclaimAgeSeconds, greaterThanOrEqualTo(serverSyncLookbackSeconds + orphanReclaimMarginSeconds));
    expect(serverSyncLookbackSeconds, 60 * 86400);
  });
  test('an orphan one second past the reclaim age on both clocks is reclaimed', () async {
    final file = await audio(name(now - orphanReclaimAgeSeconds - 1), modified: now - orphanReclaimAgeSeconds - 1);
    final sync = await ledger();
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isFalse);
  });
  for (final kind in [
    'part',
    'torn',
    'omibatch',
    'omimobilebatch',
    'unparseable',
    'filename_young',
    'mtime_young',
    'exact_reclaim_age',
    'inside_lookback',
    'inside_lookback_margin'
  ]) {
    test('excludes $kind', () async {
      final filename = switch (kind) {
        'part' => '${name(old)}.part',
        'torn' => '${name(old)}.torn',
        'omibatch' => name(old, 'omibatchphone'),
        'omimobilebatch' => name(old, 'omimobilebatch'),
        'unparseable' => 'audio_unknown.bin',
        'filename_young' => name(now - 86400),
        'exact_reclaim_age' => name(now - orphanReclaimAgeSeconds),
        // Admissible to the 60-day server lookback: the old 45-day reclaim deleted it.
        'inside_lookback' => name(now - 50 * 86400),
        'inside_lookback_margin' => name(now - serverSyncLookbackSeconds - 86400),
        _ => name(old),
      };
      final file = await audio(filename,
          modified: switch (kind) {
            'mtime_young' => now,
            'inside_lookback' => now - 50 * 86400,
            _ => old,
          });
      final sync = await ledger();
      await sync.reclaimOrphanAudio();
      expect(await file.exists(), isTrue);
    });
  }
  test('fractional filename at the reclaim-age boundary is retained', () async {
    final file = await audio(name(now - orphanReclaimAgeSeconds).replaceFirst('.bin', '.500001.bin'));
    final sync = await ledger();
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
  });
  test('legacy Limitless random-plus-millisecond filename can be reclaimed', () async {
    final sync = await ledger();
    // Created after migration: stranded bytes have no indexed custody row.
    final file = await audio('audio_limitless_opus_16000_1_fs320_r17_${old * 1000}.bin');
    expect((await census()).orphans.single.classification, 'unparseable');
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isFalse);
  });
  for (final guard in ['capture', 'mtime', 'reference', 'working']) {
    test('legacy Limitless still respects $guard exclusion', () async {
      final sync = await ledger();
      final capture = guard == 'capture' ? now - 1 : old;
      final filename =
          'audio_limitless_opus_16000_1_fs320_r17_${capture * 1000}.bin${guard == 'working' ? '.part' : ''}';
      final file = await audio(filename, modified: guard == 'mtime' ? now : old);
      if (guard == 'reference') {
        await json('wals_backup.json', {
          'wals': [row(filename)]
        });
      }
      await sync.reclaimOrphanAudio();
      expect(await file.exists(), isTrue);
    });
  }
  test('mtime exactly at the reclaim age is retained', () async {
    final file = await audio(name(old), modified: now - orphanReclaimAgeSeconds);
    final sync = await ledger();
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
  });
  test('flag read throwing retains all bytes', () async {
    final file = await audio(name(old));
    final sync = await ledger(off: () async => throw StateError('unreadable'));
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
  });
  test('queued batches delete exactly the census delta up to the pass cap', () async {
    for (var i = 0; i < 207; i++) {
      await audio(name(old - i));
    }
    final before = await census();
    final events = <Map<String, Object?>>[];
    final sync = await ledger(event: events.add);
    await sync.reclaimOrphanAudio();
    final after = await census();
    expect(before.orphans.length - after.orphans.length, 200);
    expect(events.single['deleted_files'], 200);
    expect(events.single['deleted_bytes'], 1000);
    final journal = jsonDecode(await File('${dir.path}/orphan_audio_reclaim/tombstones.json').readAsString());
    expect(journal['entries'].length, 200);
    await sync.reclaimOrphanAudio();
    expect((await census()).orphans, isEmpty);
  });
  for (final change in ['file', 'reference']) {
    test('post-tombstone $change change is revalidated before unlink', () async {
      final file = await audio(name(old));
      final sync = await ledger(afterTombstone: () {
        if (change == 'file') {
          file.writeAsBytesSync([9, 8]);
        } else {
          File('${dir.path}/wals_backup.json').writeAsStringSync(jsonEncode({
            'wals': [row(name(old))]
          }));
        }
      });
      await sync.reclaimOrphanAudio();
      expect(await file.exists(), isTrue);
    });
  }
  test('pending tombstone cannot authorize deletion after a new reference', () async {
    final file = await audio(name(old));
    final first = await ledger(afterTombstone: () => throw StateError('crash'));
    await first.reclaimOrphanAudio();
    await first.stop();
    await json('wals_backup.json', {
      'wals': [row(name(old))]
    });
    final restarted = await ledger();
    await restarted.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
  });
  test('malformed durable tombstones halt without deleting', () async {
    final file = await audio(name(old));
    await Directory('${dir.path}/orphan_audio_reclaim').create();
    await File('${dir.path}/orphan_audio_reclaim/tombstones.json').writeAsString('{');
    final sync = await ledger();
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
  });
  test('torn tombstone JSON reports journal_unavailable', () async {
    await audio(name(old));
    await Directory('${dir.path}/orphan_audio_reclaim').create();
    await File('${dir.path}/orphan_audio_reclaim/tombstones.json').writeAsString('{');
    final events = <Map<String, Object?>>[];
    final sync = await ledger(event: events.add);
    await sync.reclaimOrphanAudio();
    expect(events.single['result'], 'journal_unavailable');
  });
  test('an index reference differing only in case retains the audio', () async {
    final file = await audio(name(old));
    await json('wals_backup.json', {
      'wals': [row(name(old).toUpperCase())]
    });
    final sync = await ledger();
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
  });
  test('missing memory snapshot cannot authorize deletion', () async {
    final file = await audio(name(old));
    final sync = await ledger(scan: () => census(buckets: {}));
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
  });
  test('explicit kill switch true retains', () async {
    final file = await audio(name(old));
    final sync = await ledger(off: () async => true);
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
  });
  test('a switch closing between queue batches stops the remaining unlinks', () async {
    for (var i = 0; i < 8; i++) {
      await audio(name(old - i));
    }
    var reads = 0;
    final sync = await ledger(off: () async => ++reads >= 4);
    await sync.reclaimOrphanAudio();
    expect((await census()).orphans.length, 3);
  });
  test('later successful batch preserves an earlier sources-changed pass result', () async {
    for (var i = 0; i < 8; i++) {
      await audio(name(old - i));
    }
    var reads = 0;
    final events = <Map<String, Object?>>[];
    final sync = await ledger(
        event: events.add,
        off: () async {
          reads++;
          final prefs = await SharedPreferences.getInstance();
          if (reads == 3) {
            await prefs.setString('localRecordingJobs', jsonEncode({'unrelated.bin': 'job'}));
          }
          if (reads == 4) await prefs.remove('localRecordingJobs');
          return false;
        });
    await sync.reclaimOrphanAudio();
    expect(events.single['deleted_files'], 3);
    expect(events.single['result'], 'sources_changed');
  });
  test('failure to persist pending intent retains audio and its sidecar', () async {
    final file = await audio(name(old));
    final sidecar = File('${file.path}.geolocation.json');
    await sidecar.writeAsString('{}');
    await Directory('${dir.path}/orphan_audio_reclaim/tombstones.json.tmp').create(recursive: true);
    final sync = await ledger();
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
    expect(await sidecar.exists(), isTrue);
  });
  test('in-pass error stays failed when the ledger also stops', () async {
    final file = await audio(name(old));
    final events = <Map<String, Object?>>[];
    Future<dynamic>? stopped;
    late LocalWalSyncImpl sync;
    sync = await ledger(
        event: events.add,
        afterTombstone: () {
          stopped = sync.stop();
          throw StateError('simulated unlink failure');
        });
    await sync.reclaimOrphanAudio();
    await stopped;
    expect(await file.exists(), isTrue);
    expect(events.single['result'], 'failed');
  });
  test('crash after unlinks before completion is idempotent on a new ledger', () async {
    final file = await audio(name(old));
    final sidecar = File('${file.path}.geolocation.json');
    await sidecar.writeAsString('{}');
    final temp = Directory('${dir.path}/orphan_audio_reclaim/tombstones.json.tmp');
    final sync = await ledger(afterTombstone: () => temp.createSync());
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isFalse);
    expect(await sidecar.exists(), isFalse);
    final journal = jsonDecode(await File('${dir.path}/orphan_audio_reclaim/tombstones.json').readAsString());
    expect(journal['entries'].last['state'], 'pending');
    await sync.stop();
    await temp.delete();
    final events = <Map<String, Object?>>[];
    final restarted = await ledger(event: events.add);
    await restarted.reclaimOrphanAudio();
    expect(events.single['deleted_files'], 0);
  });
  test('configured directory outside Documents retains old audio', () async {
    final other = await Directory.systemTemp.createTemp('orphan-external-');
    addTearDown(() => other.delete(recursive: true));
    final file = File('${other.path}/${name(old)}');
    await file.writeAsBytes([1, 0, 0, 0, 7]);
    await file.setLastModified(DateTime.fromMillisecondsSinceEpoch(old * 1000));
    var scans = 0;
    final events = <Map<String, Object?>>[];
    final sync = await ledger(
        event: events.add,
        scan: () {
          scans++;
          return captureRecordingCensus(
              documents: dir.path,
              additionalDirectories: [other.path],
              memoryBuckets: {'active': []},
              phoneSeconds: now,
              currentOwner: 'owner-a');
        });
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
    expect(scans, 1);
    expect(events.single['census_complete'], isTrue);
    expect((events.single['skips'] as Map)['outside_documents'], 1);
  });
  test('legacy pending reference through a directory alias retains the same audio', () async {
    final sync = await ledger();
    final file = await audio(name(old));
    final parent = await Directory.systemTemp.createTemp('orphan-reference-alias-');
    final alias = Link('${parent.path}/documents');
    await alias.create(dir.path);
    addTearDown(() async {
      await alias.delete();
      await parent.delete();
    });
    await (await SharedPreferences.getInstance())
        .setStringList('flash_page_pending_uploads', ['${alias.path}/${name(old)}']);
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
  });
  test('symlink in the census prevents complete deletion proof', () async {
    final file = await audio(name(old));
    await Link('${dir.path}/audio_link.bin').create(file.path);
    final sync = await ledger();
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
  });
  test('unknown flag deletes nothing', () async {
    final file = await audio(name(old));
    var scans = 0;
    final events = <Map<String, Object?>>[];
    final sync = LocalWalSyncImpl(_Listener(),
        orphanForeground: () => true,
        orphanRecoveryOff: () async => true,
        orphanCensus: () {
          scans++;
          return census();
        },
        now: () => DateTime.fromMillisecondsSinceEpoch(now * 1000),
        orphanReclaimTelemetry: events.add);
    sync.start();
    await sync.walReady;
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
    expect(scans, 0);
    expect(events.single['result'], 'kill_switch');
    await sync.stop();
    (await sync.indexWorkerForTesting)?.close();
  });
  test('reclaim refreshes the framing cache while recovery is switched off', () async {
    final sync = await ledger();
    await audio(name(now - 86400));
    await sync.reclaimOrphanAudio();
    final observed = await captureRecordingCensus(
        documents: dir.path,
        memoryBuckets: {'active': []},
        phoneSeconds: now,
        currentOwner: 'owner-a',
        frameCache: sync.orphanFrameCache);
    expect((observed.summary['orphan_classification'] as Map)['frame_cache_hits'], 1);
    expect((observed.summary['orphan_classification'] as Map)['frame_files_read'], 0);
  });
  const receipt = <String, Object?>{
    'type': 'capture_committed',
    'conversation_id': 'fixture-conversation',
    'capture_root': 'fixture-root',
    'source_start': 0,
    'source_end': 50,
    'channel': 'mono',
    'clock_epoch': '0',
    'recording_session_id': null,
  };
  for (final bad in <Object>[
    [1, 2, 3],
    [{}],
    [
      {...receipt, 'future_file_ref': 'unknown.bin'}
    ]
  ]) {
    test('malformed capture journal $bad makes reclaim incomplete', () async {
      final sync = await ledger();
      final file = await audio(name(old));
      await json('capture_committed_foreign.json', bad);
      await sync.reclaimOrphanAudio();
      expect(await file.exists(), isTrue);
    });
  }
  for (final valid in <Object>[
    [],
    [receipt]
  ]) {
    test('valid capture journal $valid does not require single-owner reclaim', () async {
      final sync = await ledger();
      final file = await audio(name(old));
      await json('capture_committed_foreign.json', valid);
      await sync.reclaimOrphanAudio();
      expect(await file.exists(), isFalse);
    });
  }
  test('stopping inside a queued batch fences every unlink', () async {
    for (var i = 0; i < 8; i++) {
      await audio(name(old - i));
    }
    Future<dynamic>? stopped;
    final events = <Map<String, Object?>>[];
    late LocalWalSyncImpl sync;
    sync = await ledger(
        event: events.add,
        afterTombstone: () {
          stopped ??= sync.stop();
        });
    await sync.reclaimOrphanAudio();
    await stopped;
    expect(events.single['deleted_files'], 0);
    expect((await census()).orphans.length, 8);
  });
  for (final change in ['size', 'mtime', 'rereference', 'preference', 'generation']) {
    test('commit revalidation catches $change', () async {
      final file = await audio(name(old));
      final sync = await ledger(scan: () async {
        final snapshot = await census();
        if (change == 'size') await file.writeAsBytes([1, 2, 3]);
        if (change == 'mtime') await file.setLastModified(DateTime.now());
        if (change == 'rereference') {
          await json('wals_backup.json', {
            'wals': [row(name(old))]
          });
        }
        if (change == 'preference') {
          await (await SharedPreferences.getInstance()).setString('localRecordingJobs', jsonEncode({name(old): 'job'}));
        }
        if (change == 'generation') await SharedPreferencesUtil().saveString('uid', 'owner-b');
        return snapshot;
      });
      await sync.reclaimOrphanAudio();
      expect(await file.exists(), isTrue);
    });
  }
  test('tombstone is durable before unlink and interrupted pass retries safely', () async {
    final file = await audio(name(old));
    var interrupted = true;
    final sync = await ledger(afterTombstone: () {
      final log = File('${dir.path}/orphan_audio_reclaim/tombstones.json');
      expect(jsonDecode(log.readAsStringSync())['entries'].last['state'], 'pending');
      expect(file.existsSync(), isTrue);
      if (interrupted) throw StateError('simulated crash');
    });
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
    interrupted = false;
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isFalse);
    await sync.reclaimOrphanAudio();
  });
  test('incomplete census deletes nothing', () async {
    final file = await audio(name(old));
    final sync = await ledger();
    await File('${dir.path}/wals.json.corrupt-bad').writeAsString('{');
    await sync.reclaimOrphanAudio();
    expect(await file.exists(), isTrue);
  });
  test('admission pending, headless and background never scan', () async {
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
        orphanReclaimOff: () async => false,
        orphanReclaimTelemetry: (_) {});
    pending.start();
    await pending.reclaimOrphanAudio();
    expect(scans, 0);
    barrier.complete([]);
    await pending.walReady;
    await pending.stop();
    final headless = LocalWalSyncImpl(_Listener(), orphanCensus: scan, orphanReclaimTelemetry: (_) {});
    await headless.loadForOnDeviceWorker();
    await headless.reclaimOrphanAudio();
    expect(scans, 0);
    final background = await ledger(scan: scan, foreground: false);
    await background.reclaimOrphanAudio();
    expect(scans, 0);
  });
}
