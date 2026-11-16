import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'wal.dart';

/// The producer owns this intent until the exact file has a durable index row.
/// It precedes audio creation, so even a partial write retains its row metadata.
/// Recovery visits only this directory, never adopts historical orphan audio.
abstract final class WalWriteIntent {
  static Directory _directory(Directory documents) => Directory('${documents.path}/.wal-pending');
  static String _name(Wal wal) {
    final name = wal.filePath;
    if (name == null || name.isEmpty || name.contains('/') || name.contains('\\') || name == '.' || name == '..') {
      throw const FormatException('WAL intent requires a file name');
    }
    return name;
  }

  static File _intent(Directory documents, Wal wal) => File('${_directory(documents).path}/${_name(wal)}.json');

  static Future<bool> exists(Directory documents, String name) async =>
      await File('${_directory(documents).path}/$name.json').exists() ||
      await File('${_directory(documents).path}/$name.json.tmp').exists();

  static Future<void> write(Directory documents, Wal wal, List<int> bytes) async {
    final intent = _intent(documents, wal);
    if (await intent.exists()) throw const FileSystemException('WAL write intent already exists');
    await intent.parent.create(recursive: true);
    final tmp = File('${intent.path}.tmp');
    await tmp.create(exclusive: true);
    if (await intent.exists()) {
      await tmp.delete();
      throw const FileSystemException('WAL write intent already exists');
    }
    await tmp.writeAsString(
        jsonEncode({
          'version': 1,
          'bytes': bytes.length,
          'sha256': sha256.convert(bytes).toString(),
          'wal': wal.toJson(),
        }),
        flush: true);
    await tmp.rename(intent.path);
    wal.hasWriteIntent = true;
    final audio = File('${documents.path}/${_name(wal)}');
    await audio.create(exclusive: true);
    await audio.writeAsBytes(bytes, flush: true);
  }

  /// Only a caller that has committed the row (or is explicitly deleting it)
  /// may retire its intent. A failed retirement leaves recovery evidence.
  static Future<void> retire(Directory documents, Wal wal) async {
    await retireFile(documents, _name(wal));
    wal.hasWriteIntent = false;
  }

  static Future<void> retireFile(Directory documents, String fileName) async {
    final intent = File('${_directory(documents).path}/$fileName.json');
    if (await intent.exists()) await intent.delete();
  }

  static Future<List<Wal>> recover(Directory documents, List<Wal> indexed) async {
    final directory = _directory(documents);
    if (!await directory.exists()) return indexed;
    final recovered = List<Wal>.of(indexed);
    final known = {for (final w in indexed) (w.id, w.filePath): w};
    await for (final entry in directory.list(followLinks: false)) {
      if (entry is! File || !entry.path.endsWith('.json')) continue;
      try {
        final record = jsonDecode(await entry.readAsString()) as Map<String, dynamic>;
        if (record['version'] != 1 || record['bytes'] is! int || record['sha256'] is! String) continue;
        final wal = Wal.fromJson(Map<String, dynamic>.from(record['wal'] as Map));
        final name = _name(wal);
        if (entry.path != _intent(documents, wal).path || wal.storage != WalStorage.disk) continue;
        final existing = known[(wal.id, wal.filePath)];
        if (existing != null) {
          // Crash after index rename but before intent retirement. Only a main
          // index row with the same owner supersedes this intent; a fallback
          // backup remains recoverable evidence until a new main commit.
          if (existing.ownerUid == wal.ownerUid && existing.loadedIndexSource == '${documents.path}/wals.json') {
            await retire(documents, wal);
          } else {
            existing.hasWriteIntent = true;
          }
          continue;
        }
        final audio = File('${documents.path}/$name');
        if (!await audio.exists() || await audio.length() != record['bytes']) continue;
        if ((await sha256.bind(audio.openRead()).first).toString() != record['sha256']) continue;
        // This is recoverable audio, never proof that the index was committed.
        wal.recoveredWriteIntent = true;
        wal.hasWriteIntent = true;
        recovered.add(wal);
        known[(wal.id, wal.filePath)] = wal;
      } on FileSystemException {
        // Retain missing/partial files and their intents without guessing.
      } on FormatException {
        // Retain malformed metadata for explicit recovery, never delete audio.
      } on TypeError {
        // A future or malformed schema cannot authorize adoption or deletion.
      }
    }
    return recovered;
  }
}
