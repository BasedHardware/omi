import 'dart:io';

import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

const String exportShareLeaseFileName = '.share-lease';

final RegExp _canonicalExportDirName = RegExp(
  r'^omi-export-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$',
);

bool isOwnedExportDirectoryName(String name) => _canonicalExportDirName.hasMatch(name);

Future<void> touchExportShareLease(Directory directory) async {
  try {
    await File('${directory.path}/$exportShareLeaseFileName').writeAsString('');
  } catch (_) {}
}

Future<int> cleanupStaleExportDirectories(
  Directory tempRoot, {
  DateTime? now,
  Duration minimumAge = const Duration(hours: 24),
  int maxEntries = 200,
  int maxDeletions = 20,
  Set<String> protectedPaths = const {},
}) async {
  final cutoff = (now ?? DateTime.now()).subtract(minimumAge);
  var scanned = 0;
  var deleted = 0;
  try {
    await for (final entity in tempRoot.list(followLinks: false)) {
      if (scanned >= maxEntries || deleted >= maxDeletions) break;
      if (entity is! Directory) continue;
      if (!isOwnedExportDirectoryName(path.basename(entity.path))) continue;
      if (await FileSystemEntity.isLink(entity.path)) continue;
      scanned++;
      if (protectedPaths.contains(entity.path)) continue;
      DateTime? lastActivity;
      try {
        final lease = File('${entity.path}/$exportShareLeaseFileName');
        if (await lease.exists()) {
          lastActivity = await lease.lastModified();
        }
        lastActivity ??= (await entity.stat()).modified;
      } catch (_) {
        continue;
      }
      if (lastActivity.isAfter(cutoff)) continue;
      try {
        await entity.delete(recursive: true);
        deleted++;
      } catch (_) {}
    }
  } catch (_) {}
  return deleted;
}

typedef StaleExportSweep = Future<int> Function(Set<String> protectedPaths);

Future<void> sweepStaleExportDirectories(StaleExportSweep? sweep, {required Set<String> protectedPaths}) async {
  try {
    if (sweep != null) {
      await sweep(protectedPaths);
    } else {
      await cleanupStaleExportDirectories(await getTemporaryDirectory(), protectedPaths: protectedPaths);
    }
  } catch (_) {}
}
