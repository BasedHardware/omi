import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:pool/pool.dart';
import 'package:uuid/uuid.dart';
import '../../utils/off_ui_isolate.dart';
import '../../utils/wal_index_codec.dart';
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
    var retired = false;
    await _lock.withResource(() async {
      final intent = File('${_directory(documents).path}/$name.json');
      if (!await intent.exists()) {
        retired = true;
        return;
      }
      try {
        final record = jsonDecode(await intent.readAsString());
        if (record is! Map || record['transaction_id'] != id) return;
        if (record.containsKey('retired_rows')) {
          final backup = File('${documents.path}/wals_backup.json');
          if (await backup.exists()) {
            final content = await backup.readAsString();
            final safe = await offUiIsolate(() {
              var containsRetired = false;
              final invalid = visitWalIndex(content, (_, wal) {
                if (_isRetired(record['retired_rows'] as List, wal)) containsRetired = true;
              });
              return !invalid && !containsRetired;
            }, size: content.length, threshold: 0, debugName: 'wal_retirement_backup');
            if (!safe) return;
          }
        }
      } on FormatException {
        return; // Malformed evidence is retained, never guessed disposable.
      } on TypeError {
        return;
      }
      await intent.delete();
      retired = true;
    });
    if (retired && wal.filePath == name && wal.fileWriteId == id) _pending[wal] = false;
  }

  /// Ledger-only deletion shares the producer lock, including its file write.
  /// Inspect after acquiring it: an earlier notFound can become a late file.
  static Future<bool> deleteAudio(Directory documents, String name,
          {required bool Function() stillOwned,
          required Wal? Function() sharedWith,
          required String? transactionId,
          required Wal deletedWal,
          required String sidecarPath}) =>
      _lock.withResource(() async {
        if (!stillOwned()) return false;
        final audio = File('${documents.path}/$name');
        final type = await FileSystemEntity.type(audio.path, followLinks: false);
        if (!stillOwned()) return false;
        final intent = File('${_directory(documents).path}/$name.json');
        Map<String, dynamic>? record;
        if (await intent.exists()) {
          final decoded = jsonDecode(await intent.readAsString());
          if (decoded is! Map<String, dynamic> ||
              decoded['transaction_id'] is! String ||
              (decoded['transaction_id'] as String).isEmpty ||
              decoded['wal'] is! Map ||
              decoded['wal']['file_path'] != name) {
            return false;
          }
          record = decoded;
          // The old row owns neither these newer bytes nor their recovery
          // reference. Retire only that obsolete row, leaving the new writer.
          if (record['transaction_id'] != transactionId) return stillOwned();
        }
        final survivor = sharedWith();
        if (survivor != null) {
          if (survivor.ownerUid == null || survivor.ownerUid!.isEmpty) return false;
          if (record == null) {
            if (type != FileSystemEntityType.file) return false;
            record = {
              'version': 1,
              'bytes': await audio.length(),
              'sha256': await _hashAudio(audio),
            };
          }
          // The old index may still contain this row after a failed save.
          // Keep its exact identity until replay has durably repaired it.
          final retired = List<dynamic>.of(record['retired_rows'] as List? ?? const []);
          retired.add(deletedWal.toJson());
          record['retired_rows'] = retired;
          survivor.fileWriteId = const Uuid().v4();
          record['transaction_id'] = survivor.fileWriteId;
          record['wal'] = survivor.toJson();
          await intent.parent.create(recursive: true);
          final tmp = File('${intent.path}.tmp');
          await tmp.writeAsString(jsonEncode(record), flush: true);
          await tmp.rename(intent.path);
          markPending(survivor);
          return stillOwned();
        }
        if (type == FileSystemEntityType.file || type == FileSystemEntityType.link) {
          await audio.delete();
        } else if (type != FileSystemEntityType.notFound) {
          return false;
        }
        final sidecar = File(sidecarPath);
        if (await sidecar.exists()) await sidecar.delete();
        if (await intent.exists()) await intent.delete();
        return stillOwned();
      });

  static Future<String> _hashAudio(File audio) async {
    final bytes = await audio.readAsBytes();
    return offUiIsolate(() => sha256.convert(bytes).toString(),
        size: bytes.length, threshold: 0, debugName: 'wal_intent_hash');
  }

  // An explicit deletion also retires the exact legacy unowned disk row
  // admitted to that session; it never targets a different known owner.
  static bool _isRetired(List<dynamic> rows, Wal wal) => rows.any((value) {
        final retired = Wal.fromJson(Map<String, dynamic>.from(value as Map));
        return wal.id == retired.id &&
            wal.filePath == retired.filePath &&
            (wal.ownerUid == retired.ownerUid || (wal.ownerUid == null && retired.ownerUid != null)) &&
            wal.fileWriteId == retired.fileWriteId;
      });

  /// Shared bytes outlive a deleted row. Apply its durable retirement before
  /// assigning index tokens or publishing even the strict custody reader.
  static Future<List<Wal>> withoutRetiredRows(Directory documents, List<Wal> indexed) async {
    final directory = _directory(documents);
    if (!await directory.exists()) return indexed;
    var retained = indexed;
    await for (final entry in directory.list(followLinks: false)) {
      if (entry is! File || !entry.path.endsWith('.json')) continue;
      final dynamic decoded;
      try {
        decoded = jsonDecode(await entry.readAsString());
      } on FormatException {
        continue; // No readable retirement authority; preserve the source.
      }
      if (decoded is! Map || !decoded.containsKey('retired_rows')) continue;
      final record = Map<String, dynamic>.from(decoded);
      final survivor = Wal.fromJson(Map<String, dynamic>.from(record['wal'] as Map));
      if (record['version'] != 1 ||
          survivor.ownerUid == null ||
          survivor.ownerUid!.isEmpty ||
          survivor.fileWriteId == null ||
          record['transaction_id'] != survivor.fileWriteId ||
          entry.path != _intent(documents, survivor).path) {
        throw const FormatException('Invalid WAL retirement authority');
      }
      for (final value in record['retired_rows'] as List) {
        final retired = Wal.fromJson(Map<String, dynamic>.from(value as Map));
        if (retired.filePath != survivor.filePath) throw const FormatException('Invalid retired WAL path');
        retained = retained.where((wal) => !_isRetired([value], wal)).toList();
      }
    }
    return retained;
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
        // New transaction metadata cannot use the legacy unowned-row
        // admission rule: losing its owner must never reassign captured audio.
        if (wal.ownerUid == null || wal.ownerUid!.isEmpty) continue;
        final name = _name(wal);
        if (entry.path != _intent(documents, wal).path || wal.storage != WalStorage.disk) continue;
        final id = record['transaction_id'];
        if (id is! String || id.isEmpty || wal.fileWriteId != id) continue;
        final audio = File('${documents.path}/$name');
        if (!await audio.exists() || await audio.length() != record['bytes']) continue;
        if (await _hashAudio(audio) != record['sha256']) continue;
        final existing = known[(wal.id, wal.filePath)];
        markPending(wal);
        if (existing != null) {
          if (existing.ownerUid == wal.ownerUid &&
              existing.fileWriteId == id &&
              existing.loadedIndexSource == '${documents.path}/wals.json') {
            await retire(documents, wal);
            if (hasPending(wal)) markPending(existing);
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
