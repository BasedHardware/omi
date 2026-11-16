import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:pool/pool.dart';
import 'package:uuid/uuid.dart';
import 'wal.dart';

/// The producer owns this intent until the exact file has a durable index row.
/// It precedes audio creation, so even a partial write retains its row metadata.
/// Recovery visits only this directory, never adopts historical orphan audio.
abstract final class WalWriteIntent {
  static final _lock = Pool(1);
  static final _recovered = Expando<bool>('recoveredWalWriteIntent');
  static final _pending = Expando<bool>('pendingWalWriteIntent');
  static bool isRecovered(Wal wal) => _recovered[wal] == true;
  static bool hasPending(Wal wal) => _pending[wal] == true;
  static void markPending(Wal wal) => _pending[wal] = true;
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
    await _lock.withResource(() async {
      if (await intent.exists()) throw const FileSystemException('WAL write intent already exists');
      await intent.parent.create(recursive: true);
      final tmp = File('${intent.path}.tmp');
      await tmp.create(exclusive: true);
      wal.fileWriteId = const Uuid().v4();
      await tmp.writeAsString(
          jsonEncode({
            'version': 1,
            'transaction_id': wal.fileWriteId,
            'bytes': bytes.length,
            'sha256': sha256.convert(bytes).toString(),
            'wal': wal.toJson(),
          }),
          flush: true);
      await tmp.rename(intent.path);
      markPending(wal);
      final audio = File('${documents.path}/${_name(wal)}');
      await audio.create(exclusive: true);
      await audio.writeAsBytes(bytes, flush: true);
    });
  }

  /// A committed save may finish after this path has been deleted/reused.
  /// Retire only its captured transaction, serialized with new reservations.
  static Future<void> retire(Directory documents, Wal wal, {String? fileName, String? transactionId}) async {
    final name = fileName ?? _name(wal);
    final id = transactionId ?? wal.fileWriteId;
    if (id == null) return;
    await _lock.withResource(() async {
      final intent = File('${_directory(documents).path}/$name.json');
      if (!await intent.exists()) return;
      try {
        final record = jsonDecode(await intent.readAsString());
        if (record is! Map || record['transaction_id'] != id) return;
      } on FormatException {
        return; // Malformed evidence is retained, never guessed disposable.
      }
      await intent.delete();
    });
    if (wal.filePath == name && wal.fileWriteId == id) _pending[wal] = false;
  }

  /// Explicit ledger deletion already removed the last referenced audio file.
  static Future<void> retireFile(Directory documents, String fileName) => _lock.withResource(() async {
        final intent = File('${_directory(documents).path}/$fileName.json');
        if (await intent.exists()) await intent.delete();
      });

  /// Ledger-only deletion shares the producer lock, including its file write.
  /// Inspect after acquiring it: an earlier notFound can become a late file.
  static Future<bool> deleteAudio(Directory documents, String name,
          {required bool Function() stillOwned,
          required Wal? Function() sharedWith,
          required String? transactionId,
          required String sidecarPath}) =>
      _lock.withResource(() async {
        if (!stillOwned()) return false;
        final audio = File('${documents.path}/$name');
        final type = await FileSystemEntity.type(audio.path, followLinks: false);
        if (!stillOwned()) return false;
        final survivor = sharedWith();
        if (survivor != null) {
          final intent = File('${_directory(documents).path}/$name.json');
          if (await intent.exists()) {
            final record = jsonDecode(await intent.readAsString());
            if (record is Map<String, dynamic> && transactionId != null && record['transaction_id'] == transactionId) {
              // Transfer the recovery reference, never resurrect the deleted
              // row. A new identity protects it from that row's delayed save.
              survivor.fileWriteId = const Uuid().v4();
              record['transaction_id'] = survivor.fileWriteId;
              record['wal'] = survivor.toJson();
              final tmp = File('${intent.path}.tmp');
              await tmp.writeAsString(jsonEncode(record), flush: true);
              await tmp.rename(intent.path);
              markPending(survivor);
            }
          }
          return stillOwned();
        }
        if (type == FileSystemEntityType.file || type == FileSystemEntityType.link) {
          await audio.delete();
        } else if (type != FileSystemEntityType.notFound) {
          return false;
        }
        final sidecar = File(sidecarPath);
        if (await sidecar.exists()) await sidecar.delete();
        final intent = File('${_directory(documents).path}/$name.json');
        if (await intent.exists()) await intent.delete();
        return stillOwned();
      });

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
        // New transaction metadata cannot use the legacy unowned-row
        // admission rule: losing its owner must never reassign captured audio.
        if (wal.ownerUid == null || wal.ownerUid!.isEmpty) continue;
        final name = _name(wal);
        if (entry.path != _intent(documents, wal).path || wal.storage != WalStorage.disk) continue;
        final id = record['transaction_id'];
        if (id is! String || id.isEmpty || wal.fileWriteId != id) continue;
        final audio = File('${documents.path}/$name');
        if (!await audio.exists() || await audio.length() != record['bytes']) continue;
        if ((await sha256.bind(audio.openRead()).first).toString() != record['sha256']) continue;
        final existing = known[(wal.id, wal.filePath)];
        markPending(wal);
        if (existing != null) {
          if (existing.ownerUid == wal.ownerUid &&
              existing.fileWriteId == id &&
              existing.loadedIndexSource == '${documents.path}/wals.json') {
            await retire(documents, wal);
            continue;
          }
          // A reused filename is not a commit of these new bytes. Replace the
          // stale row under its disk token, preserving every other index row.
          recovered.remove(existing);
          wal.loadedIndexToken = existing.loadedIndexToken;
          wal.loadedIndexSource = existing.loadedIndexSource;
        }
        // This is recoverable audio, never proof that the index was committed.
        _recovered[wal] = true;
        markPending(wal);
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
