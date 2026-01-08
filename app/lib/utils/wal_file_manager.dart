import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals.dart';
import 'package:path_provider/path_provider.dart';

class WalFileManager {
  static const String _walFileName = 'wals.json';
  static const String _walBackupFileName = 'wals_backup.json';
  static const String _legacyPendingFilesKey = 'flash_page_pending_uploads';
  static const String _migrationCompletedKey = 'limitless_wal_migration_v1';

  static File? _walFile;
  static File? _walBackupFile;

  static Future<void> init() async {
    final directory =
        Platform.isMacOS ? await getApplicationSupportDirectory() : await getApplicationDocumentsDirectory();
    _walFile = File('${directory.path}/$_walFileName');
    _walBackupFile = File('${directory.path}/$_walBackupFileName');
  }

  static Future<List<Wal>> loadWals() async {
    if (_walFile == null) {
      await init();
    }

    if (_walFile == null || !_walFile!.existsSync()) {
      debugPrint('WAL file does not exist, returning empty list');
      return [];
    }

    final content = await _walFile!.readAsString();
    if (content.isEmpty) {
      debugPrint('WAL file is empty, returning empty list');
      return [];
    }

    final jsonData = jsonDecode(content);
    if (jsonData is! Map<String, dynamic> || jsonData['wals'] is! List) {
      debugPrint('Invalid WAL file format, returning empty list');
      return [];
    }

    final walsList = jsonData['wals'] as List;
    return Wal.fromJsonList(walsList);
  }

  static Future<bool> saveWals(List<Wal> wals) async {
    if (_walFile == null) {
      await init();
    }

    if (_walFile == null) {
      debugPrint('WAL file is null, cannot save');
      return false;
    }

    await _createBackup();

    final jsonData = {
      'version': 1,
      'timestamp': DateTime.now().millisecondsSinceEpoch,
      'wals': wals.map((wal) => wal.toJson()).toList(),
    };

    final jsonString = jsonEncode(jsonData);
    await _walFile!.writeAsString(jsonString);

    debugPrint('Successfully saved ${wals.length} WALs to file');
    return true;
  }

  static Future<void> _createBackup() async {
    if (_walFile != null && _walFile!.existsSync() && _walBackupFile != null) {
      await _walFile!.copy(_walBackupFile!.path);
    }
  }

  /// Load WALs from backup file
  static Future<List<Wal>> _loadFromBackup() async {
    if (_walBackupFile == null || !_walBackupFile!.existsSync()) {
      return [];
    }

    final content = await _walBackupFile!.readAsString();
    if (content.isEmpty) {
      return [];
    }

    final jsonData = jsonDecode(content);
    if (jsonData is! Map<String, dynamic> || jsonData['wals'] is! List) {
      return [];
    }

    final walsList = jsonData['wals'] as List;
    return Wal.fromJsonList(walsList);
  }

  static Future<bool> migrateFromPreferences(List<Wal> prefsWals) async {
    if (prefsWals.isEmpty) {
      debugPrint('No WALs to migrate from preferences');
      return true;
    }

    final success = await saveWals(prefsWals);
    if (success) {
      debugPrint('Successfully migrated ${prefsWals.length} WALs from preferences to file');
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
    debugPrint('Cleared all WAL files');
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

    return {
      'mainFileSize': mainFileSize,
      'backupFileSize': backupFileSize,
    };
  }

  /// Migrate legacy Limitless pending files from SharedPreferences to the new WAL system.
  /// This handles files that were saved under the old 'flash_page_pending_uploads' key.
  /// The old implementation stored full absolute paths like '/path/to/docs/audio_limitless_...bin'
  /// Returns the number of files migrated.
  static Future<int> migrateLegacyLimitlessFiles(List<Wal> existingWals) async {
    final prefs = SharedPreferencesUtil();

    // Check if migration was already done
    if (prefs.getBool(_migrationCompletedKey)) {
      debugPrint('WalFileManager: Legacy Limitless migration already completed');
      return 0;
    }

    // Get legacy pending files from SharedPreferences (stored as full absolute paths)
    final legacyFiles = prefs.getStringList(_legacyPendingFilesKey);
    if (legacyFiles.isEmpty) {
      debugPrint('WalFileManager: No legacy Limitless files to migrate');
      prefs.saveBool(_migrationCompletedKey, true);
      return 0;
    }

    debugPrint('WalFileManager: Found ${legacyFiles.length} legacy Limitless files to migrate');

    int migratedCount = 0;
    final newWals = <Wal>[];

    for (final fullPath in legacyFiles) {
      try {
        // Old implementation stored full absolute paths
        final file = File(fullPath);
        if (!file.existsSync()) {
          debugPrint('WalFileManager: Legacy file not found, skipping: $fullPath');
          continue;
        }

        // Extract just the filename for WAL storage (consistent with new system)
        final fileName = fullPath.split('/').last;

        // Check if this file is already tracked in existing WALs
        final alreadyTracked = existingWals.any((wal) =>
            wal.filePath == fullPath ||
            wal.filePath == fileName ||
            (wal.filePath != null && wal.filePath!.endsWith(fileName)));

        if (alreadyTracked) {
          debugPrint('WalFileManager: File already tracked, skipping: $fileName');
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
        debugPrint('WalFileManager: Migrated legacy file: $fileName (${seconds}s)');
      } catch (e) {
        debugPrint('WalFileManager: Error migrating file $fullPath: $e');
      }
    }

    // Save migrated WALs
    if (newWals.isNotEmpty) {
      final allWals = List<Wal>.from(existingWals)..addAll(newWals);
      await saveWals(allWals);
      debugPrint('WalFileManager: Saved ${newWals.length} migrated WALs');
    }

    // Clear legacy SharedPreferences and mark migration complete
    prefs.saveStringList(_legacyPendingFilesKey, []);
    prefs.saveBool(_migrationCompletedKey, true);

    debugPrint('WalFileManager: Legacy Limitless migration complete. Migrated $migratedCount files.');
    return migratedCount;
  }

  /// Also migrate any WALs that might be in inconsistent state from old implementation.
  /// This fixes WALs that have storage=flashPage but already have a local file.
  static Future<bool> migrateInconsistentWals(List<Wal> wals) async {
    bool needsSave = false;

    for (var wal in wals) {
      // Case 1: FlashPage WAL that has a file locally - was downloaded but not transitioned
      if (wal.storage == WalStorage.flashPage && wal.filePath != null && wal.filePath!.isNotEmpty) {
        debugPrint('WalFileManager: Fixing inconsistent WAL ${wal.id} - has file but storage=flashPage');
        wal.storage = WalStorage.disk;
        wal.originalStorage = WalStorage.flashPage;
        needsSave = true;
      }

      // Case 2: Limitless device WAL on disk without originalStorage tracking
      if (wal.storage == WalStorage.disk &&
          wal.originalStorage == null &&
          (wal.deviceModel?.toLowerCase().contains('limitless') == true ||
              wal.filePath?.contains('limitless') == true)) {
        debugPrint('WalFileManager: Setting originalStorage=flashPage for Limitless WAL ${wal.id}');
        wal.originalStorage = WalStorage.flashPage;
        needsSave = true;
      }
    }

    if (needsSave) {
      await saveWals(wals);
      debugPrint('WalFileManager: Saved WALs after inconsistency fixes');
    }

    return needsSave;
  }
}
