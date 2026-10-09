import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/settings/data_export_files.dart';

const _uuidA = 'omi-export-11111111-2222-4333-8444-555555555555';
const _uuidB = 'omi-export-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const _uuidC = 'omi-export-00000000-1111-4222-8333-444444444444';

Future<Directory> _exportDir(Directory root, String name) async {
  final dir = Directory('${root.path}/$name');
  await dir.create(recursive: true);
  await File('${dir.path}/omi-export.json').writeAsString('{}');
  return dir;
}

void main() {
  late Directory tempRoot;

  setUp(() async {
    tempRoot = await Directory.systemTemp.createTemp('export-cleanup-test');
  });

  tearDown(() async {
    if (await tempRoot.exists()) await tempRoot.delete(recursive: true);
  });

  test('removes aged canonical export directories including partials', () async {
    final stale = await _exportDir(tempRoot, _uuidA);
    await File('${stale.path}/chunk.part').writeAsString('partial');
    final staleB = await _exportDir(tempRoot, _uuidB);

    final deleted = await cleanupStaleExportDirectories(tempRoot, now: DateTime.now().add(const Duration(days: 2)));

    expect(deleted, 2);
    expect(await stale.exists(), isFalse);
    expect(await staleB.exists(), isFalse);
  });

  test('keeps recent canonical directories and unrelated lookalikes', () async {
    final recent = await _exportDir(tempRoot, _uuidA);
    final lookalike = await _exportDir(tempRoot, 'omi-export-not-a-uuid');
    final loosePrefix = await _exportDir(tempRoot, 'omi-export-11111111-2222-4333-8444-555555555555-extra');

    final deleted = await cleanupStaleExportDirectories(tempRoot);

    expect(deleted, 0);
    expect(await recent.exists(), isTrue);
    expect(await lookalike.exists(), isTrue);
    expect(await loosePrefix.exists(), isTrue);
  });

  test('never follows symlinks even with canonical names', () async {
    final target = await _exportDir(tempRoot, 'real-target');
    await Link('${tempRoot.path}/$_uuidA').create(target.path);

    final deleted = await cleanupStaleExportDirectories(tempRoot, now: DateTime.now().add(const Duration(days: 2)));

    expect(deleted, 0);
    expect(await FileSystemEntity.isLink('${tempRoot.path}/$_uuidA'), isTrue);
    expect(await target.exists(), isTrue);
  });

  test('protected paths survive even when aged past the window', () async {
    final active = await _exportDir(tempRoot, _uuidA);
    final other = await _exportDir(tempRoot, _uuidB);

    final deleted = await cleanupStaleExportDirectories(
      tempRoot,
      now: DateTime.now().add(const Duration(days: 2)),
      protectedPaths: {active.path},
    );

    expect(deleted, 1);
    expect(await active.exists(), isTrue);
    expect(await other.exists(), isFalse);
  });

  test('an aged share lease, not a fresh directory mtime, decides deletion', () async {
    final leased = await _exportDir(tempRoot, _uuidA);
    final lease = File('${leased.path}/$exportShareLeaseFileName');
    await lease.writeAsString('');
    await lease.setLastModified(DateTime.now().subtract(const Duration(days: 3)));

    final deleted = await cleanupStaleExportDirectories(tempRoot);

    expect(deleted, 1);
    expect(await leased.exists(), isFalse);
  });

  test('deletion budget bounds a single sweep', () async {
    for (var i = 0; i < 6; i++) {
      await _exportDir(tempRoot, 'omi-export-11111111-2222-4333-8444-${i.toString().padLeft(12, '0')}');
    }

    final deleted = await cleanupStaleExportDirectories(
      tempRoot,
      now: DateTime.now().add(const Duration(days: 2)),
      maxDeletions: 2,
    );

    expect(deleted, 2);
    expect(await tempRoot.list().where((e) => e is Directory).length, 4);
  });

  test('touchExportShareLease refreshes the marker used for aging', () async {
    final dir = await _exportDir(tempRoot, _uuidA);
    final lease = File('${dir.path}/$exportShareLeaseFileName');

    await touchExportShareLease(dir);

    expect(await lease.exists(), isTrue);
    final stamp = await lease.lastModified();
    expect(DateTime.now().difference(stamp).inMinutes, lessThan(5));
  });

  test('unrelated temp-root entries never starve the owned-candidate budget', () async {
    for (var i = 0; i < 250; i++) {
      await _exportDir(tempRoot, 'scratch-$i');
    }
    await File('${tempRoot.path}/loose-file.txt').writeAsString('x');
    final stale = await _exportDir(tempRoot, _uuidA);

    final deleted = await cleanupStaleExportDirectories(
      tempRoot,
      now: DateTime.now().add(const Duration(days: 2)),
      maxEntries: 5,
    );

    expect(deleted, 1);
    expect(await stale.exists(), isFalse);
  });

  test('non-uuid canonical-looking names are ignored', () async {
    await _exportDir(tempRoot, 'omi-export-11111111-2222-1333-8444-555555555555');
    await _exportDir(tempRoot, _uuidC);

    final deleted = await cleanupStaleExportDirectories(tempRoot, now: DateTime.now().add(const Duration(days: 2)));

    expect(deleted, 1);
    expect(await Directory('${tempRoot.path}/omi-export-11111111-2222-1333-8444-555555555555').exists(), isTrue);
  });
}
