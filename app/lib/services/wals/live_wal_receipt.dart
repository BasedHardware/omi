// Saves captured ownership before live audio reaches disk. A receipt proves
// local bytes for index replay only. It is never a server or pendant receipt.
import 'dart:collection';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as path;
import 'package:uuid/uuid.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/off_ui_isolate.dart';
import 'package:omi/utils/wal_index_row.dart';
import 'wal.dart';

typedef LiveWalBinding = ({String id, String owner, String digest});
typedef LiveWalIndexEntry = ({LiveWalBinding binding, Object row});
typedef LiveWalReceiptPurgeResult = ({int removed, bool referenceScanIncomplete});

class LiveWalPurgeSnapshot {
  LiveWalPurgeSnapshot(this.basenames, this.revision, this.documentsPath);
  Set<String> basenames;
  int revision;
  final String documentsPath;
  bool refreshFailed = false;
}

class _LiveWalMemoryProof {
  const _LiveWalMemoryProof(this.basename, this.length, this.binding);
  final String basename;
  final int length;
  final LiveWalBinding binding;
}

enum LiveWalWithheld { invalid, deletedOwner, missingAudio, contentMismatch }

typedef LiveWalReplay = ({List<Wal> rows, Map<LiveWalWithheld, int> withheld, bool budgetExhausted, String? nextAfter});

class LiveWalReceipt {
  static const MethodChannel _durabilityChannel = MethodChannel('com.omi/live_wal_receipt_durability');
  static Future<void> Function(Directory directory)? syncDirectoryForTesting;
  static const directoryName = '.wal-live-receipts';
  static const writeEnabled = !bool.fromEnvironment('OMI_LIVE_WAL_RECEIPT_OFF');
  static const purgeEnabled = !bool.fromEnvironment('OMI_LIVE_WAL_RECEIPT_PURGE_OFF');
  static Future<void> Function(File file, String body)? writeReceiptForTesting;
  static const _pending = '.json';
  static const _stagingDirectory = 'staging';
  static const _retiredDirectory = 'retired';
  static const _maxEntries = 128;
  static const maxUnindexedPurgeBatchEntries = _maxEntries;
  static const maxInventorySourceEntries = _maxEntries;
  static const _maxReceiptBytes = 16 * 1024;
  static const maxInventoryReceiptBytes = _maxReceiptBytes;
  static const _maxReplayBytes = 32 * 1024 * 1024;
  // A known affected Documents directory contained about 164k leaked audio
  // files. Keep the enumeration finite while allowing that supported scale.
  static const _maxIndexDirectoryEntries = 262144;
  static const _maxQuarantineIndexes = 4096;
  // Large, valid indexes and several quarantine generations can exceed 32 MiB.
  // Keep the reference scan bounded while allowing ordinary repair history.
  static const _maxPurgeIndexBytes = 128 * 1024 * 1024;
  static final _idPattern = RegExp(r'^[a-f0-9]{32}$');
  static final _managedNamePattern =
      RegExp(r'_wr([a-f0-9]{32})(?:_clke[0-9a-z]{1,32})?_[^_]+\.bin$', caseSensitive: false);
  static final _clockSuffix = RegExp(r'_clke[0-9a-z]{1,32}$');
  static final _digestPattern = RegExp(r'^[a-f0-9]{64}$');
  static final Set<String> _confirmedDirectoryParents = <String>{};
  static final Expando<_LiveWalMemoryProof> _writerProofs = Expando<_LiveWalMemoryProof>('live_wal_writer_proof');

  static Directory directory(Directory documents) => Directory(path.join(documents.path, directoryName));

  static bool _safeName(String name) =>
      name.startsWith('audio_') && name.endsWith('.bin') && !name.contains(RegExp(r'[/\\\x00]'));

  /// A receipt-managed filename must never fall through to heuristic owner
  /// inference, even if the directory or both indexes disappear.
  static bool isManagedBasename(String name) => _managedNamePattern.hasMatch(name);

  /// Staging files and retired receipts never count toward replay work.
  static String? _receiptBasename(String entryPath) {
    final entryName = path.basename(entryPath);
    if (!entryName.endsWith(_pending)) return null;
    final name = entryName.substring(0, entryName.length - _pending.length);
    return _safeName(name) && isManagedBasename(name) ? name : null;
  }

  static String newId() => const Uuid().v4().replaceAll('-', '');

  /// Keep the existing field positions for record-WAL handoff and the
  /// trailing timestamp for sync admission. Both timestamps come from the
  /// same original name, including fractional capture evidence.
  static String uniqueName(String basename, String id) {
    if (!_safeName(basename) || !_idPattern.hasMatch(id)) throw const FormatException('invalid live WAL name');
    final timestampStart = basename.lastIndexOf('_');
    final timestamp = basename.substring(timestampStart + 1, basename.length - 4);
    final originalFields = basename.substring(0, timestampStart);
    final clock = _clockSuffix.firstMatch(originalFields);
    final fields = originalFields.substring(0, clock?.start ?? originalFields.length);
    // Both Opus variants use the same codec on the wire. Its packet duration
    // is already carried by the explicit fs field.
    final wireFields = fields.replaceFirst('_opus_fs320_', '_opus_');
    return '${wireFields}_${timestamp}_wr$id${clock?.group(0) ?? ''}_$timestamp.bin';
  }

  static File _receipt(Directory documents, String name) => File(path.join(directory(documents).path, name + _pending));

  static Future<void> _syncDirectory(Directory directory) async {
    final override = syncDirectoryForTesting;
    if (override != null) return override(directory);
    await _durabilityChannel.invokeMethod<void>('syncDirectory', {'path': directory.path});
  }

  static Future<void> _syncConfirmedDirectory(Directory directory) async {
    await _syncDirectory(directory);
    _confirmedDirectoryParents.add(directory.path);
  }

  static Future<void> syncAudioParentDirectory(File audio) => _syncDirectory(audio.parent);

  static Future<bool> hasPendingReceipt(File audio) => _receipt(audio.parent, path.basename(audio.path)).exists();

  static Future<void> _writeTemporaryReceipt(File file, String body) async {
    final override = writeReceiptForTesting;
    if (override != null) return override(file, body);
    await file.writeAsString(body, flush: true);
  }

  static Future<Directory> _checkedDirectory(Directory directory) async {
    final existed = await FileSystemEntity.type(directory.path, followLinks: false) == FileSystemEntityType.directory;
    await directory.create(recursive: true);
    if (await FileSystemEntity.type(directory.path, followLinks: false) != FileSystemEntityType.directory) {
      throw const FileSystemException('invalid live WAL receipt directory');
    }
    if (!existed) await _syncConfirmedDirectory(directory.parent);
    return directory;
  }

  static Future<String> _digest(List<int> bytes) => offUiIsolate(() => sha256.convert(bytes).toString(),
      size: bytes.length, threshold: 64 * 1024, debugName: 'live_wal_receipt_digest');

  static Future<String> prepare(File audio, Wal wal, String id, List<int> bytes) async {
    final name = path.basename(audio.path);
    final digest = await _digest(bytes);
    final pending = _receipt(audio.parent, name);
    await _checkedDirectory(pending.parent);
    final staging = await _checkedDirectory(Directory(path.join(pending.parent.path, _stagingDirectory)));
    // A new reserved audio entry is created for each flush, so persist its
    // parent before receipt publication. Cache the stable receipt directory
    // only after a successful barrier; retries still sync an unconfirmed dir.
    await _syncDirectory(audio.parent);
    if (!_confirmedDirectoryParents.contains(pending.parent.path)) {
      await _syncConfirmedDirectory(pending.parent);
    }
    final temporary = File(path.join(staging.path, name + _pending));
    // Freeze the policy after the digest finishes. Any pending live file is
    // replayed held because later policy tightening may have been interrupted.
    final fields = wal.toJson()
      ..['storage'] = 'disk'
      ..['file_path'] = name
      ..['live_file_write_id'] = id
      ..['file_sha256'] = digest
      ..['captured_on_device_only'] = wal.capturedOnDeviceOnly ?? wal.onDeviceOnly;
    final body = jsonEncode({'version': 1, 'length': bytes.length, 'wal': fields});
    if (utf8.encode(body).length > _maxReceiptBytes) throw const FormatException('live WAL receipt too large');
    if (await pending.exists()) throw const FileSystemException('live WAL receipt already exists');
    try {
      await _writeTemporaryReceipt(temporary, body);
      await temporary.rename(pending.path);
      // The rename crosses directories, so persist both the removed staging name
      // and the newly published pending name before audio bytes can be written.
      await _syncDirectory(staging);
      await _syncConfirmedDirectory(pending.parent);
    } catch (error, stackTrace) {
      // A partial staging write is not scanned or replayed. Retire it and sync
      // its directory so retries cannot accumulate abandoned receipt blobs.
      try {
        if (await temporary.exists()) await temporary.delete();
        await _syncDirectory(staging);
      } catch (_) {
        // Preserve the original publication error; staging is never authority.
      }
      // Audio has not been written yet. Best-effort retirement prevents a
      // failed durability barrier from leaving a receipt that blocks reuse.
      try {
        if (await pending.exists()) await pending.delete();
        await _syncDirectory(pending.parent);
      } catch (_) {
        // Any surviving final sidecar is still content-checked and fail-closed.
      }
      Error.throwWithStackTrace(error, stackTrace);
    }
    return digest;
  }

  static LiveWalBinding? _binding(String name, Object? row) {
    if (row is! Map || row['storage'] != 'disk' || row['file_path'] != name) return null;
    final id = row['live_file_write_id'], owner = row['owner_uid'], digest = row['file_sha256'];
    if (id is! String ||
        !_idPattern.hasMatch(id) ||
        !name.contains('_wr${id}_') ||
        owner is! String ||
        owner.isEmpty ||
        owner == 'legacy' ||
        digest is! String ||
        !_digestPattern.hasMatch(digest)) {
      return null;
    }
    return (id: id, owner: owner, digest: digest);
  }

  static Map<String, LiveWalIndexEntry> indexBindings(Object? envelope) =>
      envelope is Map ? bindings(envelope['wals']) : {};

  static Map<String, LiveWalIndexEntry> bindings(Object? rows) {
    final result = <String, LiveWalIndexEntry>{};
    final collisions = <String>{};
    if (rows is! Iterable) return result;
    for (final row in rows) {
      if (row is! Map || row['file_path'] is! String) continue;
      final name = row['file_path'] as String;
      if (!name.contains('_wr') || !_safeName(name)) continue;
      final binding = _binding(name, row);
      if (result.containsKey(name) || binding == null) {
        collisions.add(name);
        continue;
      }
      result[name] = (binding: binding, row: row);
    }
    collisions.forEach(result.remove);
    return result;
  }

  static Future<({Wal wal, int length, LiveWalBinding binding})?> _read(File entry, String name) async {
    if (await FileSystemEntity.type(entry.path, followLinks: false) != FileSystemEntityType.file ||
        await entry.length() > _maxReceiptBytes) {
      return null;
    }
    final decoded = jsonDecode(await entry.readAsString());
    if (decoded is! Map || decoded['version'] != 1 || decoded['length'] is! int) return null;
    final length = decoded['length'] as int;
    final fields = decoded['wal'];
    final binding = _binding(name, fields);
    if (binding == null || fields is! Map<String, dynamic> || length <= 0 || length > _maxReplayBytes) return null;
    final codec = fields['codec'];
    if (fields['total_frames'] is! int ||
        (fields['total_frames'] as int) <= 0 ||
        fields['on_device_only'] is! bool ||
        fields['captured_on_device_only'] is! bool ||
        fields['hold_for_user'] is! bool ||
        (fields['status'] != 'miss' && fields['status'] != 'synced') ||
        codec is! String ||
        mapCodecToName(mapNameToCodec(codec)) != codec ||
        fields['timer_start'] is! int) {
      return null;
    }
    return (wal: decodeWalIndexRow(fields), length: length, binding: binding);
  }

  static Future<bool> isValidPendingReceipt(File entry) async {
    final name = _receiptBasename(entry.path);
    return name != null && await _read(entry, name) != null;
  }

  static Future<bool> _matchesAudio(File audio, int length, String expectedDigest) async {
    final handle = await audio.open();
    final List<int> bytes;
    try {
      bytes = await handle.read(length);
    } finally {
      await handle.close();
    }
    return bytes.length == length && await _digest(bytes) == expectedDigest && await audio.length() == length;
  }

  static Future<bool> _matchesPurgeAudio(File audio, int length, String digest) async {
    if (await FileSystemEntity.type(audio.path, followLinks: false) != FileSystemEntityType.file) return false;
    final before = await audio.stat();
    if (before.size != length || !await _matchesAudio(audio, length, digest)) return false;
    final after = await audio.stat();
    return after.size == before.size &&
        after.changed == before.changed &&
        after.modified == before.modified &&
        await FileSystemEntity.type(audio.path, followLinks: false) == FileSystemEntityType.file;
  }

  /// Validates an unindexed purge against a writer-owned snapshot and, when a
  /// receipt has since disappeared, this process's exact write proof.
  static Future<LiveWalPurgeSnapshot> capturePurgeSnapshot(File primary, File backup, int revision) async =>
      LiveWalPurgeSnapshot(await _indexedBasenames(primary, backup), revision, primary.parent.path);

  static Future<bool> matchesPendingPurgeInSnapshot(File audio, Wal wal, LiveWalPurgeSnapshot snapshot) async {
    if (!purgeEnabled || !isManagedBasename(path.basename(audio.path)) || audio.parent.path != snapshot.documentsPath) {
      return false;
    }
    final name = path.basename(audio.path);
    final expected = _binding(name, wal.toJson());
    if (expected == null || snapshot.basenames.contains(name.toLowerCase())) return false;
    final pending = _receipt(audio.parent, name);
    int? length;
    try {
      if (await FileSystemEntity.type(pending.parent.path, followLinks: false) == FileSystemEntityType.directory) {
        final record = await _read(pending, name);
        if (record != null && record.binding == expected) length = record.length;
      }
    } catch (_) {
      // The exact write proof below is limited to this in-memory WAL object.
    }
    final memoryProof = _writerProofs[wal];
    if (length == null && memoryProof?.basename == name && memoryProof?.binding == expected) {
      length = memoryProof!.length;
    }
    if (length == null) return false;
    return await _matchesPurgeAudio(audio, length, expected.digest);
  }

  static void rememberWriterProof(Wal wal, String basename, int length, LiveWalBinding binding) {
    _writerProofs[wal] = _LiveWalMemoryProof(basename, length, binding);
  }

  static Future<Set<String>> _indexedBasenames(File primary, File backup) async {
    final names = <String>{};
    final indexes = [primary, backup];
    // Index repair can discard a malformed row while retaining its file
    // reference in the quarantine copy. Missing canonical files alone do
    // not establish that the basename was unreferenced.
    final quarantinePrefixes = indexes.map((index) => walIndexQuarantinePrefix(index.path)).toList();
    var directoryEntries = 0;
    var quarantineCount = 0;
    await for (final entry in primary.parent.list(followLinks: false)) {
      if (++directoryEntries > _maxIndexDirectoryEntries) {
        throw const FileSystemException('WAL index reference scan exceeded directory entry limit');
      }
      if (quarantinePrefixes.any((prefix) => entry.path.startsWith(prefix))) {
        if (entry is! File) throw const FileSystemException('invalid quarantined WAL index path');
        if (++quarantineCount > _maxQuarantineIndexes) {
          throw const FileSystemException('WAL index reference scan exceeded quarantine limit');
        }
        indexes.add(entry);
      }
    }
    var bytesRemaining = _maxPurgeIndexBytes;
    for (final index in indexes) {
      final type = await FileSystemEntity.type(index.path, followLinks: false);
      if (type == FileSystemEntityType.notFound && (index == primary || index == backup)) continue;
      if (type != FileSystemEntityType.file) throw const FileSystemException('invalid WAL index path');
      final length = await index.length();
      if (length > bytesRemaining) throw const FileSystemException('WAL index reference scan exceeded byte limit');
      bytesRemaining -= length;
      final content = await index.readAsString();
      names.addAll(await offUiIsolate(() {
        final decoded = jsonDecode(content);
        if (decoded is! Map || decoded['wals'] is! List) throw const FormatException('invalid WAL index schema');
        final rows = decoded['wals'] as List;
        final basenames = <String>[];
        for (final row in rows) {
          final filePath = (row as Map)['file_path'];
          if (filePath != null) basenames.add(path.basename(filePath as String).toLowerCase());
        }
        return basenames;
      }, size: content.length, threshold: 0, debugName: 'live_wal_purge_index'));
    }
    return names;
  }

  /// Delete only pending receipt audio that has no live or durable index
  /// reference. The caller holds the index writer lock during validation.
  static Future<LiveWalReceiptPurgeResult> purgeUnindexed(
    File primary, {
    required Set<String> owners,
    required Set<String> indexedNames,
    required Set<String> reservedNames,
    required bool Function(String) mayDelete,
    required List<File> entries,
    Set<String> protectedNames = const <String>{},
  }) async {
    if (!purgeEnabled || owners.isEmpty) return (removed: 0, referenceScanIncomplete: false);
    final documents = primary.parent;
    var removed = 0;
    var scanComplete = true;
    try {
      for (final entry in entries) {
        final name = _receiptBasename(entry.path);
        if (name == null || reservedNames.contains(name.toLowerCase()) || protectedNames.contains(name.toLowerCase())) {
          continue;
        }
        final ({Wal wal, int length, LiveWalBinding binding})? record;
        try {
          record = await _read(entry, name);
        } catch (_) {
          continue;
        }
        if (record == null || !owners.contains(record.binding.owner) || !mayDelete(name)) continue;
        if (indexedNames.contains(name.toLowerCase())) continue;
        try {
          final audio = File(path.join(documents.path, name));
          if (!await _matchesPurgeAudio(audio, record.length, record.binding.digest) || !mayDelete(name)) continue;
          await audio.delete();
          removed++;
          await retireAfterFileDeletion(audio, record.wal);
        } catch (_) {/* Keep uncertain files and leave failed cleanup for a later purge. */}
      }
    } catch (_) {
      scanComplete = false;
      /* An unreadable index or receipt gives no deletion authority. */
    }
    return (removed: removed, referenceScanIncomplete: !scanComplete);
  }

  /// Enumerate cheap receipt paths as bounded pages. Callers process each page
  /// under the index lock after WAL readiness, so a large archive cannot hold
  /// startup or one index-writer critical section for the full scan.
  static Stream<List<File>> pendingReceiptPages(Directory documents) async* {
    final pending = directory(documents);
    final type = await FileSystemEntity.type(pending.path, followLinks: false);
    if (type == FileSystemEntityType.notFound) return;
    if (type != FileSystemEntityType.directory) throw const FileSystemException('invalid live WAL receipt directory');

    var page = <File>[];
    await for (final entry in pending.list(followLinks: false)) {
      if (entry is! File || _receiptBasename(entry.path) == null) continue;
      page.add(entry);
      if (page.length == maxUnindexedPurgeBatchEntries) {
        yield List<File>.unmodifiable(page);
        page = <File>[];
      }
    }
    if (page.isNotEmpty) yield List<File>.unmodifiable(page);
  }

  static Future<LiveWalReplay> recover(
    Directory documents, {
    required Set<String> knownBasenames,
    required Set<String> deletedOwners,
    String? after,
  }) async {
    final rows = <Wal>[];
    final withheld = <LiveWalWithheld, int>{};
    void reject(LiveWalWithheld reason) => withheld.update(reason, (count) => count + 1, ifAbsent: () => 1);

    final pending = directory(documents);
    final type = await FileSystemEntity.type(pending.path, followLinks: false);
    if (type == FileSystemEntityType.notFound) {
      return (rows: rows, withheld: withheld, budgetExhausted: false, nextAfter: null);
    }
    if (type != FileSystemEntityType.directory) throw const FileSystemException('invalid live WAL receipt directory');

    // Directory order is unspecified. Select a bounded page ordered by the
    // random transaction ID, starting after the last attempted entry and
    // wrapping once. Invalid and missing entries cannot starve future launches.
    final candidates = SplayTreeMap<String, ({File file, String name})>((a, b) {
      if (after != null) {
        final aBefore = a.compareTo(after) <= 0, bBefore = b.compareTo(after) <= 0;
        if (aBefore != bBefore) return aBefore ? 1 : -1;
      }
      return a.compareTo(b);
    });
    await for (final entry in pending.list(followLinks: false)) {
      final name = _receiptBasename(entry.path);
      if (entry is! File || name == null || knownBasenames.contains(name.toLowerCase())) continue;
      final id = _managedNamePattern.firstMatch(name)!.group(1)!;
      candidates[id] = (file: entry, name: name);
      if (candidates.length > _maxEntries + 1) candidates.remove(candidates.lastKey());
    }

    var bytesRemaining = _maxReplayBytes;
    var exhausted = candidates.length > _maxEntries;
    String? lastAttempted;
    for (final candidate in candidates.entries.take(_maxEntries)) {
      final previous = lastAttempted;
      lastAttempted = candidate.key;
      final (file: entry, :name) = candidate.value;
      try {
        final record = await _read(entry, name);
        if (record == null) {
          reject(LiveWalWithheld.invalid);
          continue;
        }
        if (deletedOwners.contains(record.binding.owner)) {
          reject(LiveWalWithheld.deletedOwner);
          continue;
        }
        final audio = File(path.join(documents.path, name));
        if (await FileSystemEntity.type(audio.path, followLinks: false) != FileSystemEntityType.file) {
          reject(LiveWalWithheld.missingAudio);
          continue;
        }
        if (await audio.length() != record.length) {
          reject(LiveWalWithheld.contentMismatch);
          continue;
        }
        if (record.length > bytesRemaining) {
          exhausted = true;
          lastAttempted = previous;
          break;
        }
        bytesRemaining -= record.length;
        if (!await _matchesAudio(audio, record.length, record.binding.digest)) {
          reject(LiveWalWithheld.contentMismatch);
          continue;
        }
        final wal = record.wal
          ..holdForUser = true
          ..status = WalStatus.miss
          ..syncedAt = 0
          ..liveRingId = null
          ..liveOrdinalStart = null
          ..liveOrdinalEnd = null
          ..liveConnectionEpoch = null
          ..liveDeviceId = null;
        knownBasenames.add(name.toLowerCase());
        rows.add(wal);
      } catch (_) {
        reject(LiveWalWithheld.invalid);
      }
    }
    return (rows: rows, withheld: withheld, budgetExhausted: exhausted, nextAfter: exhausted ? lastAttempted : null);
  }

  static Future<Map<String, LiveWalIndexEntry>> _readIndexBindings(File file) async {
    final content = await file.readAsString();
    return offUiIsolate(() => indexBindings(jsonDecode(content)),
        size: content.length, threshold: 0, debugName: 'live_wal_receipt_index');
  }

  static Future<void> _flushBackupCopy(File file) async {
    final handle = await file.open(mode: FileMode.append);
    try {
      await handle.flush();
    } finally {
      await handle.close();
    }
  }

  /// Run only after both restart index generations have durably committed the
  /// matching record. Best effort: a later startup can try again.
  static Future<void> retireCommitted(File primaryFile, File backupFile) async {
    try {
      final pending = directory(backupFile.parent);
      if (!await pending.exists() || !await primaryFile.exists() || !await backupFile.exists()) return;
      final main = await _readIndexBindings(primaryFile);
      final backup = await _readIndexBindings(backupFile);
      if (main.isEmpty || backup.isEmpty) return;
      var visited = 0;
      var backupFlushed = false;
      await for (final entry in pending.list(followLinks: false)) {
        final name = _receiptBasename(entry.path);
        if (entry is! File || name == null) continue;
        final primary = main[name], previous = backup[name];
        if (primary == null || previous == null || primary.binding != previous.binding) continue;
        if (++visited > _maxEntries) break;
        try {
          decodeWalIndexRow(primary.row);
          decodeWalIndexRow(previous.row);
          if ((await _read(entry, name))?.binding != primary.binding) continue;
          if (!backupFlushed) {
            // The existing writer copies its backup without a durability
            // barrier. Pay a sync only when a receipt can actually retire.
            await _flushBackupCopy(backupFile);
            backupFlushed = true;
          }
          await entry.delete();
        } catch (_) {/* Keep uncertain receipts for a later retry. */}
      }
    } catch (_) {/* Receipt maintenance never invalidates an index commit. */}
  }

  /// A shared file remains on disk after a row is deleted. First retire the
  /// matching receipt's replay authority so it cannot recreate that row.
  static Future<bool> retireForSharedDeletion(File audio, Wal wal) async {
    final name = path.basename(audio.path);
    final pending = _receipt(audio.parent, name);
    if (wal.liveFileWriteId == null || !await pending.exists()) return true;
    final expected = _binding(name, wal.toJson());
    if (expected == null || (await _read(pending, name))?.binding != expected) return false;
    final retired = await _checkedDirectory(Directory(path.join(pending.parent.path, _retiredDirectory)));
    await pending.rename(path.join(retired.path, name + _pending));
    return true;
  }

  /// Physical bytes have already been deleted. Never remove a mismatched
  /// receipt: a different transaction may still need that reservation.
  static Future<void> retireAfterFileDeletion(File audio, Wal wal) async {
    final name = path.basename(audio.path);
    final expected = _binding(name, wal.toJson());
    if (expected == null) return;
    final pending = _receipt(audio.parent, name);
    try {
      if ((await _read(pending, name))?.binding == expected) await pending.delete();
    } catch (_) {/* Missing audio cannot be replayed. */}
  }
}
