// Saves captured ownership before live audio reaches disk. A receipt proves
// local bytes for index replay only. It is never a server or pendant receipt.
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as path;
import 'package:uuid/uuid.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/off_ui_isolate.dart';
import 'package:omi/utils/wal_index_row.dart';
import 'wal.dart';

typedef LiveWalBinding = ({String id, String owner, String digest});
typedef LiveWalIndexEntry = ({LiveWalBinding binding, Object row});

enum LiveWalWithheld { invalid, deletedOwner, missingAudio, contentMismatch }

typedef LiveWalReplay = ({List<Wal> rows, Map<LiveWalWithheld, int> withheld, bool budgetExhausted});

class LiveWalReceipt {
  static const directoryName = '.wal-live-receipts';
  static const writeEnabled = !bool.fromEnvironment('OMI_LIVE_WAL_RECEIPT_OFF');
  static const _pending = '.json';
  static const _retired = '.retired';
  static const _temporary = '.json.tmp';
  static const _maxEntries = 128;
  static const _maxReceiptBytes = 16 * 1024;
  static const _maxReplayBytes = 32 * 1024 * 1024;
  static final _idPattern = RegExp(r'^[a-f0-9]{32}$');
  static final _managedNamePattern = RegExp(r'_wr[a-f0-9]{32}_[^_]+\.bin$', caseSensitive: false);
  static final _digestPattern = RegExp(r'^[a-f0-9]{64}$');

  static Directory directory(Directory documents) => Directory(path.join(documents.path, directoryName));

  static bool _safeName(String name) =>
      name.startsWith('audio_') && name.endsWith('.bin') && !name.contains(RegExp(r'[/\\\x00]'));

  /// A receipt-managed filename must never fall through to heuristic owner
  /// inference, even if the directory or both indexes disappear.
  static bool isManagedBasename(String name) => _managedNamePattern.hasMatch(name);

  /// Identify pending and retired receipts without trusting their payload.
  static String? _receiptBasename(String entryPath) {
    final entryName = path.basename(entryPath);
    for (final suffix in [_temporary, _pending, _retired]) {
      if (!entryName.endsWith(suffix)) continue;
      final name = entryName.substring(0, entryName.length - suffix.length);
      if (_safeName(name) && isManagedBasename(name)) return name;
    }
    return null;
  }

  static String newId() => const Uuid().v4().replaceAll('-', '');

  /// Keep the numeric timestamp as the last token on the upload wire.
  static String uniqueName(String basename, String id) {
    if (!_safeName(basename) || !_idPattern.hasMatch(id)) throw const FormatException('invalid live WAL name');
    final timestamp = basename.lastIndexOf('_');
    return '${basename.substring(0, timestamp)}_wr$id${basename.substring(timestamp)}';
  }

  static File _receipt(Directory documents, String name, [String suffix = _pending]) =>
      File(path.join(directory(documents).path, name + suffix));

  static Future<String> prepare(File audio, Wal wal, String id, List<int> bytes) async {
    final name = path.basename(audio.path);
    final digest = await offUiIsolate(() => sha256.convert(bytes).toString(),
        size: bytes.length, threshold: 64 * 1024, debugName: 'live_wal_receipt_digest');
    final pending = _receipt(audio.parent, name);
    await pending.parent.create(recursive: true);
    if (await FileSystemEntity.type(pending.parent.path, followLinks: false) != FileSystemEntityType.directory) {
      throw const FileSystemException('invalid live WAL receipt directory');
    }
    final temporary = _receipt(audio.parent, name, _temporary);
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
    if (await pending.exists() || await audio.exists()) throw const FileSystemException('live WAL name already in use');
    await temporary.writeAsString(body, flush: true);
    await temporary.rename(pending.path);
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

  static Future<LiveWalReplay> recover(
    Directory documents, {
    required Set<String> knownBasenames,
    required Set<String> deletedOwners,
  }) async {
    final rows = <Wal>[];
    final withheld = <LiveWalWithheld, int>{};
    void reject(LiveWalWithheld reason) => withheld.update(reason, (count) => count + 1, ifAbsent: () => 1);

    var visited = 0, bytesRemaining = _maxReplayBytes, exhausted = false;
    final pending = directory(documents);
    final type = await FileSystemEntity.type(pending.path, followLinks: false);
    if (type == FileSystemEntityType.notFound) return (rows: rows, withheld: withheld, budgetExhausted: exhausted);
    if (type != FileSystemEntityType.directory) throw const FileSystemException('invalid live WAL receipt directory');
    await for (final entry in pending.list(followLinks: false)) {
      if (++visited > _maxEntries) {
        exhausted = true;
        break;
      }
      final name = _receiptBasename(entry.path);
      if (entry is! File || !entry.path.endsWith(_pending) || name == null) continue;
      if (knownBasenames.contains(name.toLowerCase())) continue;
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
          break;
        }
        bytesRemaining -= record.length;
        final digest = await sha256.bind(audio.openRead(0, record.length)).first;
        if (digest.toString() != record.binding.digest || await audio.length() != record.length) {
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
    return (rows: rows, withheld: withheld, budgetExhausted: exhausted);
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
  /// matching record. Best effort: the next save or startup can try again.
  static Future<void> retireCommitted(
      File backupFile, Map<String, LiveWalIndexEntry> main, Map<String, LiveWalIndexEntry> backup) async {
    if (main.isEmpty || backup.isEmpty) return;
    try {
      final pending = directory(backupFile.parent);
      if (!await pending.exists()) return;
      var visited = 0;
      var backupFlushed = false;
      await for (final entry in pending.list(followLinks: false)) {
        if (++visited > _maxEntries) break;
        final name = _receiptBasename(entry.path);
        if (entry is! File || !entry.path.endsWith(_pending) || name == null) continue;
        final primary = main[name], previous = backup[name];
        if (primary == null || previous == null || primary.binding != previous.binding) continue;
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
    await pending.rename(_receipt(audio.parent, name, _retired).path);
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
