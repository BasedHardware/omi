import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:omi/services/wals.dart';
import 'package:path_provider/path_provider.dart';

class WalFileManager {
  static const String _walFileName = 'wals.json';
  static const String _walBackupFileName = 'wals_backup.json';

  static File? _walFile;
  static File? _walBackupFile;

  /// Initialize the file manager and get file references
  static Future<void> init() async {
    try {
      final directory = await getApplicationDocumentsDirectory();
      _walFile = File('${directory.path}/$_walFileName');
      _walBackupFile = File('${directory.path}/$_walBackupFileName');
    } catch (e) {
      debugPrint('Error initializing WalFileManager: $e');
    }
  }

  /// Load WALs from file
  static Future<List<Wal>> loadWals() async {
    try {
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
    } catch (e) {
      debugPrint('Error loading WALs from file: $e');

      // Try to load from backup
      try {
        return await _loadFromBackup();
      } catch (backupError) {
        debugPrint('Error loading WALs from backup: $backupError');
        return [];
      }
    }
  }

  /// Save WALs to file
  static Future<bool> saveWals(List<Wal> wals) async {
    try {
      if (_walFile == null) {
        await init();
      }

      if (_walFile == null) {
        debugPrint('WAL file is null, cannot save');
        return false;
      }

      // Create backup before saving
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
    } catch (e) {
      debugPrint('Error saving WALs to file: $e');
      return false;
    }
  }

  /// Create backup of current WAL file
  static Future<void> _createBackup() async {
    try {
      if (_walFile != null && _walFile!.existsSync() && _walBackupFile != null) {
        await _walFile!.copy(_walBackupFile!.path);
      }
    } catch (e) {
      debugPrint('Error creating WAL backup: $e');
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

  /// Migrate WALs from SharedPreferences to file
  static Future<bool> migrateFromPreferences(List<Wal> prefsWals) async {
    try {
      if (prefsWals.isEmpty) {
        debugPrint('No WALs to migrate from preferences');
        return true;
      }

      final success = await saveWals(prefsWals);
      if (success) {
        debugPrint('Successfully migrated ${prefsWals.length} WALs from preferences to file');
      }
      return success;
    } catch (e) {
      debugPrint('Error migrating WALs from preferences: $e');
      return false;
    }
  }

  /// Clear all WAL data (both file and backup)
  static Future<void> clearAll() async {
    try {
      if (_walFile != null && _walFile!.existsSync()) {
        await _walFile!.delete();
      }
      if (_walBackupFile != null && _walBackupFile!.existsSync()) {
        await _walBackupFile!.delete();
      }
      debugPrint('Cleared all WAL files');
    } catch (e) {
      debugPrint('Error clearing WAL files: $e');
    }
  }

  /// Get file size information
  static Future<Map<String, int>> getFileInfo() async {
    try {
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
    } catch (e) {
      debugPrint('Error getting WAL file info: $e');
      return {'mainFileSize': 0, 'backupFileSize': 0};
    }
  }
}
