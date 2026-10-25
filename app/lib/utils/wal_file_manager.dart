import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'package:path_provider/path_provider.dart';
import 'package:pool/pool.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/services/wals/mobile_batch_buffer.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/off_ui_isolate.dart';
import 'package:omi/startup/boot_journal.dart';

class WalFileManager {
  static const String _walFileName = 'wals.json';
  static const String _walBackupFileName = 'wals_backup.json';
  static const String _legacyPendingFilesKey = 'flash_page_pending_uploads';
  static const String _migrationCompletedKey = 'limitless_wal_migration_v1';

  static File? _walFile;
  static File? _walBackupFile;
  static final _saveLock = Pool(1);

  static Future<void> init() async {
    final directory = await getApplicationDocumentsDirectory();
    _walFile = File('${directory.path}/$_walFileName');
    _walBackupFile = File('${directory.path}/$_walBackupFileName');
  }

  static Future<List<Wal>> loadWals() async {
    if (_walFile == null) {
      await init();
    }

    final loaded = _walFile != null && await _walFile!.exists() ? await _loadIndex(_walFile!) : null;
    final indexed = loaded ?? await _loadFromBackup();
    return MobileBatchBuffer.recover(_walFile!.parent, indexed);
  }

  /// Null means the index is unusable; a partially valid index retains every
  /// readable entry and archives the original bytes before writing the repair.
  static Future<List<Wal>?> _loadIndex(File file) async {
    try {
      final content = await file.readAsString();
      final decoded = jsonDecode(content);
      if (decoded is! Map<String, dynamic> || decoded['wals'] is! List) {
        await _quarantineIndex(file, 'invalid_schema');
        return null;
      }
      final loaded = <Wal>[];
      var invalid = false;
      for (final entry in decoded['wals'] as List) {
        try {
          if (entry is! Map<String, dynamic>) throw const FormatException();
          // Old indices can omit new optional fields, but a WAL without its
          // identity or with a wrong scalar type must never enter sync admission.
          if (entry['timer_start'] is! int || entry['codec'] is! String) throw const FormatException();
          for (final key in [
            'channel',
            'sample_rate',
            'seconds',
            'storage_offset',
            'storage_total_bytes',
            'file_num',
            'total_frames',
            'synced_frame_offset',
            'retry_count',
            'last_retry_at',
            'uploaded_at',
            'source_frame_start',
            'source_clock_epoch',
            'live_ring_id',
            'live_ordinal_start',
            'live_ordinal_end',
          ]) {
            if (entry[key] != null && entry[key] is! int) throw const FormatException();
          }
          for (final key in [
            'file_path',
            'device',
            'device_model',
            'conversation_id',
            'recording_session_id',
            'owner_uid',
            'capture_root',
            'job_id',
          ]) {
            if (entry[key] != null && entry[key] is! String) throw const FormatException();
          }
          loaded.add(Wal.fromJson(entry));
        } catch (_) {
          invalid = true;
        }
      }
      if (invalid) {
        await _quarantineIndex(file, 'invalid_entry');
        if (identical(file, _walFile)) {
          try {
            await _saveWals(loaded);
          } catch (_) {
            // The archived source remains available for another recovery.
          }
        }
      }
      return loaded;
    } catch (_) {
      await _quarantineIndex(file, 'unreadable');
      return null;
    }
  }

  static Future<void> _quarantineIndex(File file, String reason) async {
    try {
      if (await file.exists()) {
        await file.rename('${file.path}.corrupt-${DateTime.now().microsecondsSinceEpoch}');
      }
      await BootJournal.instance.record('quarantine:${file.uri.pathSegments.last}', reason);
    } catch (_) {
      await BootJournal.instance.record('quarantine:${file.uri.pathSegments.last}', 'rename_failed');
    }
  }

  /// Indexes at or above this size are JSON-encoded on a background isolate.
  /// The index is rewritten whole on every save and grows with every recording
  /// a user keeps, so encoding it on the UI isolate stalls scrolling during
  /// sync. Small indexes stay inline: spawning costs more than it saves.
  @visibleForTesting
  static int backgroundEncodeThreshold = 200;

  /// The save queued behind the one in flight, if any. Every caller passes a
  /// full snapshot of the in-memory index, and the last snapshot written always
  /// wins on disk, so a newer request may replace a queued (not yet started)
  /// one: the final file is identical and the superseded caller resolves only
  /// after a write at least as new as its own. The newest superseded snapshot
  /// becomes the backup, exactly as if each save had been written in turn.
  static _QueuedSave? _queued;

  /// Length and modification time of the index as this process last wrote it.
  /// While the file still matches, it is known-valid JSON (we encoded it), so
  /// the backup can be copied without reading and decoding the whole index.
  static ({String path, int length, DateTime modified})? _lastWritten;

  static Future<bool> saveWals(List<Wal> wals) {
    final queued = _queued;
    if (queued != null) {
      queued.superseded = queued.wals;
      queued.wals = wals;
      return queued.completer.future;
    }
    final save = _QueuedSave(wals);
    _queued = save;
    _saveLock.withResource(() {
      if (identical(_queued, save)) _queued = null;
      return _saveWals(save.wals, superseded: save.superseded);
    }).then(save.completer.complete, onError: save.completer.completeError);
    return save.completer.future;
  }

  static Future<bool> _saveWals(List<Wal> wals, {List<Wal>? superseded}) async {
    if (_walFile == null) {
      await init();
    }

    if (_walFile == null) {
      Logger.debug('WAL file is null, cannot save');
      return false;
    }

    if (superseded != null && _walBackupFile != null) {
      // Serial saves would have left the newest superseded snapshot on disk as
      // the backup; write it there directly. Best effort, like _createBackup:
      // a backup failure must never block the index write.
      try {
        final backupTmp = File('${_walBackupFile!.path}.tmp');
        await backupTmp.writeAsString(await _encodeIndex(superseded), flush: true);
        await backupTmp.rename(_walBackupFile!.path);
      } on FileSystemException catch (e) {
        Logger.debug('WalFileManager: Failed to write superseded backup: $e');
      }
    } else {
      await _createBackup();
    }

    final jsonString = await _encodeIndex(wals);
    final tmp = File('${_walFile!.path}.tmp');
    await tmp.writeAsString(jsonString, flush: true);
    await tmp.rename(_walFile!.path);
    await _recordWrite(_walFile!);

    Logger.debug('Successfully saved ${wals.length} WALs to file');
    return true;
  }

  static Future<String> _encodeIndex(List<Wal> wals) {
    // Copy WAL objects into the worker before expanding them into thousands
    // of JSON maps. Encoding alone leaves that allocation work on the UI.
    return offUiIsolate(() {
      final jsonData = {
        'version': 1,
        'timestamp': DateTime.now().millisecondsSinceEpoch,
        'wals': wals.map((wal) => wal.toJson()).toList(),
      };
      return jsonEncode(jsonData);
    }, size: wals.length, threshold: backgroundEncodeThreshold, debugName: 'wal_index_encode');
  }

  static Future<void> _recordWrite(File file) async {
    try {
      final stat = await FileStat.stat(file.path);
      _lastWritten = (path: file.path, length: stat.size, modified: stat.modified);
    } on FileSystemException {
      _lastWritten = null;
    }
  }

  static Future<void> _createBackup() async {
    try {
      final walFile = _walFile;
      final backupFile = _walBackupFile;
      if (walFile == null || backupFile == null) return;
      final stat = await FileStat.stat(walFile.path);
      if (stat.type == FileSystemEntityType.notFound) return;
      final last = _lastWritten;
      final unchangedSinceOurWrite =
          last != null && last.path == walFile.path && last.length == stat.size && last.modified == stat.modified;
      if (!unchangedSinceOurWrite) {
        // Written by an earlier process or changed under us: prove it parses
        // before it may replace the last good backup.
        final content = await walFile.readAsString();
        if (content.isEmpty) return;
        jsonDecode(content);
      }
      await walFile.copy(backupFile.path);
    } on FileSystemException catch (e) {
      Logger.debug('WalFileManager: Failed to create backup: $e');
    } on FormatException catch (e) {
      Logger.debug('WalFileManager: Not backing up unreadable WAL file: $e');
    }
  }

  /// Load WALs from backup file
  static Future<List<Wal>> _loadFromBackup() async {
    if (_walBackupFile == null || !_walBackupFile!.existsSync()) {
      return [];
    }
    return await _loadIndex(_walBackupFile!) ?? [];
  }

  static Future<bool> migrateFromPreferences(List<Wal> prefsWals) async {
    if (prefsWals.isEmpty) {
      Logger.debug('No WALs to migrate from preferences');
      return true;
    }

    final success = await saveWals(prefsWals);
    if (success) {
      Logger.debug('Successfully migrated ${prefsWals.length} WALs from preferences to file');
    }
    return success;
  }

  static Future<void> clearAll() async {
    if (_walFile != null && _walFile!.existsSync()) {
      await _walFile!.delete();
    }
    if (_walBackupFile != null && _walBackupFile!.existsSync()) {
      await _walBackupFile!.delete();
    }
    Logger.debug('Cleared all WAL files');
  }

  static Future<Map<String, int>> getFileInfo() async {
    int mainFileSize = 0;
    int backupFileSize = 0;

    if (_walFile != null && _walFile!.existsSync()) {
      mainFileSize = await _walFile!.length();
    }

    if (_walBackupFile != null && _walBackupFile!.existsSync()) {
      backupFileSize = await _walBackupFile!.length();
    }

    return {'mainFileSize': mainFileSize, 'backupFileSize': backupFileSize};
  }

  /// Migrate legacy Limitless pending files from SharedPreferences to the new WAL system.
  /// This handles files that were saved under the old 'flash_page_pending_uploads' key.
  /// The old implementation stored full absolute paths like '/path/to/docs/audio_limitless_...bin'
  /// Returns the number of files migrated.
  static Future<int> migrateLegacyLimitlessFiles(List<Wal> existingWals) async {
    final prefs = SharedPreferencesUtil();

    // Check if migration was already done
    if (prefs.getBool(_migrationCompletedKey)) {
      Logger.debug('WalFileManager: Legacy Limitless migration already completed');
      return 0;
    }

    // Get legacy pending files from SharedPreferences (stored as full absolute paths)
    final legacyFiles = prefs.getStringList(_legacyPendingFilesKey);
    if (legacyFiles.isEmpty) {
      Logger.debug('WalFileManager: No legacy Limitless files to migrate');
      prefs.saveBool(_migrationCompletedKey, true);
      return 0;
    }

    Logger.debug('WalFileManager: Found ${legacyFiles.length} legacy Limitless files to migrate');

    int migratedCount = 0;
    final newWals = <Wal>[];

    for (final fullPath in legacyFiles) {
      try {
        // Old implementation stored full absolute paths
        final file = File(fullPath);
        if (!file.existsSync()) {
          Logger.debug('WalFileManager: Legacy file not found, skipping: $fullPath');
          continue;
        }

        // Extract just the filename for WAL storage (consistent with new system)
        final fileName = fullPath.split('/').last;

        // Check if this file is already tracked in existing WALs
        final alreadyTracked = existingWals.any(
          (wal) =>
              wal.filePath == fullPath ||
              wal.filePath == fileName ||
              (wal.filePath != null && wal.filePath!.endsWith(fileName)),
        );

        if (alreadyTracked) {
          Logger.debug('WalFileManager: File already tracked, skipping: $fileName');
          continue;
        }

        // Parse info from filename
        // Expected format: audio_limitless_opus_16000_1_fs320_r{random}_{timestampMs}.bin
        int timerStart = DateTime.now().millisecondsSinceEpoch ~/ 1000;
        int seconds = 30; // Default estimate

        // Try to extract timestamp from filename (13-digit millisecond timestamp)
        final timestampMatch = RegExp(r'_(\d{13})\.bin$').firstMatch(fileName);
        if (timestampMatch != null) {
          timerStart = int.parse(timestampMatch.group(1)!) ~/ 1000;
        }

        // Estimate duration from file size (~8KB per second for opus)
        final fileSize = await file.length();
        seconds = (fileSize / 8000).ceil();
        if (seconds < 1) seconds = 1;

        // Create WAL entry for this file
        // Store just the filename (new system uses Wal.getFilePath() to resolve full path)
        final wal = Wal(
          timerStart: timerStart,
          codec: BleAudioCodec.opus,
          channel: 1,
          sampleRate: 16000,
          seconds: seconds,
          status: WalStatus.miss,
          storage: WalStorage.disk,
          filePath: fileName,
          device: 'limitless',
          deviceModel: 'Limitless',
          originalStorage: WalStorage.flashPage,
        );

        newWals.add(wal);
        migratedCount++;
        Logger.debug('WalFileManager: Migrated legacy file: $fileName (${seconds}s)');
      } catch (e) {
        Logger.debug('WalFileManager: Error migrating file $fullPath: $e');
      }
    }

    // Save migrated WALs
    if (newWals.isNotEmpty) {
      final allWals = List<Wal>.from(existingWals)..addAll(newWals);
      await saveWals(allWals);
      Logger.debug('WalFileManager: Saved ${newWals.length} migrated WALs');
    }

    // Clear legacy SharedPreferences and mark migration complete
    prefs.saveStringList(_legacyPendingFilesKey, []);
    prefs.saveBool(_migrationCompletedKey, true);

    Logger.debug('WalFileManager: Legacy Limitless migration complete. Migrated $migratedCount files.');
    return migratedCount;
  }

  /// Also migrate any WALs that might be in inconsistent state from old implementation.
  /// This fixes WALs that have storage=flashPage but already have a local file.
  static Future<bool> migrateInconsistentWals(List<Wal> wals) async {
    bool needsSave = false;

    for (var wal in wals) {
      // Case 1: FlashPage WAL that has a file locally - was downloaded but not transitioned
      if (wal.storage == WalStorage.flashPage && wal.filePath != null && wal.filePath!.isNotEmpty) {
        Logger.debug('WalFileManager: Fixing inconsistent WAL ${wal.id} - has file but storage=flashPage');
        wal.storage = WalStorage.disk;
        wal.originalStorage = WalStorage.flashPage;
        needsSave = true;
      }

      // Case 2: Limitless device WAL on disk without originalStorage tracking
      if (wal.storage == WalStorage.disk &&
          wal.originalStorage == null &&
          (wal.deviceModel?.toLowerCase().contains('limitless') == true ||
              wal.filePath?.contains('limitless') == true)) {
        Logger.debug('WalFileManager: Setting originalStorage=flashPage for Limitless WAL ${wal.id}');
        wal.originalStorage = WalStorage.flashPage;
        needsSave = true;
      }
    }

    if (needsSave) {
      await saveWals(wals);
      Logger.debug('WalFileManager: Saved WALs after inconsistency fixes');
    }

    return needsSave;
  }
}

class _QueuedSave {
  _QueuedSave(this.wals);

  List<Wal> wals;
  List<Wal>? superseded;
  final completer = Completer<bool>();
}
