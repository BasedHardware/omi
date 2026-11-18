import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/wals/recording_inventory.dart';

void main() {
  for (final fields in <Map<String, Object?>>[
    {'storage': 'future'},
    {'storage': 7},
    {'storage': false},
    {
      'storage': 'mem',
      'file_path': {'file': 'hidden.bin'}
    },
    {'storage': 'disk'},
    {'storage': 'disk', 'file_path': ''},
    {
      'storage': 'sdcard',
      'file_path': ['hidden.bin']
    },
  ]) {
    test('ambiguous WAL reference schema fences census: $fields', () async {
      final dir = await Directory.systemTemp.createTemp('orphan-schema-');
      addTearDown(() => dir.delete(recursive: true));
      await File('${dir.path}/wals.json').writeAsString(jsonEncode({
        'wals': [
          {'timer_start': 1794873600, 'codec': 'opus', 'owner_uid': 'owner', ...fields}
        ]
      }));
      final census = await captureRecordingCensus(
          documents: dir.path, memoryBuckets: {'active': []}, phoneSeconds: 1794873600, currentOwner: 'owner');
      expect(census.complete, isFalse);
      expect(census.summary['invalid_minimum_schema_rows'], 1);
    });
  }

  test('diagnostics classify owner-proven orphan audio without exporting file identifiers', () async {
    final dir = await Directory.systemTemp.createTemp('orphan-contract-');
    addTearDown(() => dir.delete(recursive: true));
    const now = 1794873600;
    await File('${dir.path}/wals.json').writeAsString(jsonEncode({
      'wals': [
        {
          'file_path': 'indexed.bin',
          'timer_start': now,
          'codec': 'opus_fs320',
          'storage': 'disk',
          'owner_uid': 'private-owner',
          'status': 'synced',
        }
      ]
    }));
    await File('${dir.path}/audio_private-device_opus_fs320_16000_1_fs320_$now.bin').writeAsBytes([1, 0, 0, 0, 7]);
    final result = await captureRecordingInventory(
        documents: dir.path, memoryBuckets: {'active': []}, phoneSeconds: now, currentOwner: 'private-owner');
    expect(result['orphan_classification'], isNotNull,
        reason: 'support diagnostics must expose the same recovery classification');
    expect((result['orphan_classification'] as Map)['classes']['recoverable']['count'], 1);
    expect(jsonEncode(result), isNot(contains('private')));
    expect(jsonEncode(result), isNot(contains(dir.path)));
    expect(jsonEncode(result), isNot(contains('audio_private-device_')));
  });
}
