import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/recording_inventory.dart';
import 'package:omi/utils/off_ui_isolate.dart';

void main() {
  late Directory dir;
  const now = 1794744000;
  Map<String, Object?> row(String file, {int time = now, String status = 'miss'}) => {
        'file_path': file,
        'timer_start': time,
        'status': status,
        'storage': 'disk',
        'codec': 'opus_fs320',
        'total_frames': 100,
        'seconds': 2,
        'storage_total_bytes': 3,
        'owner_uid': 'private-owner',
        'transcript': 'private-content',
        'title': 'private-content',
      };
  Future<File> file(String name, List<int> bytes) => File('${dir.path}/$name').writeAsBytes(bytes);
  Future<File> json(String name, Object value) => File('${dir.path}/$name').writeAsString(jsonEncode(value));
  setUp(() async {
    dir = await Directory.systemTemp.createTemp('read-only-recording-inventory');
  });
  tearDown(() async {
    await dir.delete(recursive: true);
  });

  test('census finds orphan, missing row, retired bucket and journals without modifying files', () async {
    await file('audio_private-active.bin', [1, 2, 3]);
    await file('audio_private-retired.bin', [1, 2, 3, 4]);
    await file('audio_private-orphan.bin', [1, 2, 3, 4, 5]);
    await file('audio_private-journal.bin', [1, 2]);
    await json('wals.json', {
      'wals': [row('audio_private-active.bin'), row('audio_private-missing.bin', time: 0)]
    });
    await json('wals_backup.json', {
      'wals': [row('audio_private-retired.bin', time: now + 86401)]
    });
    await json('audio_private-journal.bin.batch-journal', row('audio_private-journal.bin', time: 51));
    await json('omibatch_owners.json', {'audio_private-active.bin': 'private-owner'});
    await json('boot_stages.json', [
      {'stage': 'quarantine:wals.json', 'state': 'invalid_entry', 'at_ms': 123}
    ]);
    final before = <String, (List<int>, DateTime)>{};
    await for (final entry in dir.list()) {
      if (entry is File) before[entry.path] = (await entry.readAsBytes(), (await entry.stat()).modified);
    }
    final result = await captureRecordingInventory(
        documents: dir.path,
        phoneSeconds: now,
        currentOwner: 'private-owner',
        freeBytes: 123456,
        memoryBuckets: {
          'retired': [
            const RecordingInventoryRow(
                status: 'miss',
                captureSeconds: now + 86401,
                audioSeconds: 2,
                indexBytes: 4,
                disk: true,
                filePath: 'audio_private-retired.bin',
                owner: 'private-other-owner')
          ]
        });
    final directory = (result['directories'] as List).single as Map;
    expect(directory['audio_files'], 4);
    expect(directory['audio_bytes'], 14);
    expect(directory['referenced_audio_files'], 3);
    expect(directory['unreferenced_audio_files'], 1);
    expect(directory['unreferenced_audio_bytes'], 5);
    final buckets = result['buckets'] as Map;
    expect(buckets['main_index']['rows'], 2);
    expect(buckets['main_index']['rows_with_missing_file'], 1);
    expect(buckets['main_index']['by_capture_time'], {'plausible': 1, 'zero': 1});
    expect(buckets['retired']['by_capture_time'], {'future': 1});
    expect(buckets['retired']['by_owner_class'], {'foreign': 1});
    expect(buckets['batch_journal']['by_capture_time'], {'before_2024': 1});
    expect(result['free_disk_bytes'], 123456);
    expect(result['last_recorded_loader_or_recovery'],
        {'category': 'index_quarantine', 'result': 'invalid_entry', 'at_ms': 123});
    expect(result['orphan_census_complete'], true);
    expect(jsonEncode(result), isNot(contains('private')));
    expect(jsonEncode(result), isNot(contains('file_path')));
    expect(directory['oldest_creation_ms'], null);
    for (final entry in before.entries) {
      expect(await File(entry.key).readAsBytes(), entry.value.$1);
      expect((await File(entry.key).stat()).modified, entry.value.$2);
    }
    expect((await dir.list().toList()).length, before.length);
  });
  test('quarantine, legacy preferences and malformed indexes stay read-only and explicitly incomplete', () async {
    await file('audio_private-legacy.bin', [9]);
    await json('wals.json.corrupt-123', {
      'wals': [row('audio_private-missing.bin', time: -5)]
    });
    await File('${dir.path}/wals.json').writeAsString('{invalid');
    final result = await captureRecordingInventory(
        documents: dir.path,
        phoneSeconds: now,
        memoryBuckets: {},
        legacyFiles: ['${dir.path}/audio_private-legacy.bin'],
        legacyJobs: jsonEncode({'audio_private-missing.bin': 'private-job'}),
        corruptLegacyJobs: '{invalid');
    expect((result['buckets'] as Map)['quarantine_index']['rows'], 1);
    expect((result['buckets'] as Map)['legacy_preference_files']['rows'], 1);
    expect(result['unreadable_metadata_files'], 2);
    expect(result['orphan_census_complete'], false);
    expect(await File('${dir.path}/wals.json').readAsString(), '{invalid');
    expect(await File('${dir.path}/wals.json.corrupt-123').exists(), true);
    expect(jsonEncode(result), isNot(contains('private')));
  });
  test('large 16000-row index decode and summaries run off UI with no fallback', () async {
    await json('wals.json', {'wals': List.generate(16000, (i) => row('audio_private-$i.bin'))});
    final fallbacks = offUiIsolateFallbacks, workers = offUiIsolateWorkerCompletions;
    final result = await captureRecordingInventory(documents: dir.path, phoneSeconds: now, memoryBuckets: {});
    expect((result['buckets'] as Map)['main_index']['rows'], 16000);
    expect((result['buckets'] as Map)['main_index']['rows_with_missing_file'], 16000);
    expect(offUiIsolateFallbacks, fallbacks);
    expect(offUiIsolateWorkerCompletions, greaterThanOrEqualTo(workers + 2));
  });
  test('referenced historical filename is not declared missing by the audio-name filter', () async {
    await file('historical-recording.raw', [1, 2]);
    await json('wals.json', {
      'wals': [row('historical-recording.raw')]
    });
    final result = await captureRecordingInventory(documents: dir.path, phoneSeconds: now, memoryBuckets: {});
    expect((result['buckets'] as Map)['main_index']['rows_with_missing_file'], 0);
    expect(result['unique_missing_file_references'], 0);
  });
  test('malformed rows and absent disk references cannot assert a complete orphan census', () async {
    await file('audio_private-orphan.bin', [1]);
    await json('wals.json', {
      'wals': [
        'private-malformed-row',
        {...row('ignored'), 'file_path': null}
      ]
    });
    final result = await captureRecordingInventory(documents: dir.path, phoneSeconds: now, memoryBuckets: {});
    expect(result['invalid_minimum_schema_rows'], 2);
    expect(result['rows_without_file_reference'], 1);
    expect(result['orphan_census_complete'], false);
    expect(jsonEncode(result), isNot(contains('private')));
  });
  test('directory walk stats every file across parallel batches, preserving counts and bytes', () async {
    // More files than one stat batch, plus a partial final batch.
    const count = 64 * 3 + 7;
    for (var i = 0; i < count; i++) {
      await file('audio_private-$i.bin', List.filled(i % 5 + 1, 0));
    }
    await json('wals.json', {
      'wals': [row('audio_private-0.bin'), row('audio_private-1.bin')]
    });
    final result = await captureRecordingInventory(documents: dir.path, phoneSeconds: now, memoryBuckets: {});
    final documents = (result['directories'] as List).single as Map;
    expect(documents['audio_files'], count);
    expect(documents['regular_files_seen'], count + 1);
    expect(documents['referenced_audio_files'], 2);
    expect(documents['unreferenced_audio_files'], count - 2);
    expect(documents['audio_bytes'], List.generate(count, (i) => i % 5 + 1).fold<int>(0, (a, b) => a + b));
    expect(result['file_stat_errors'], 0);
    expect((result['buckets'] as Map)['main_index']['rows_with_missing_file'], 0);
  });
}
