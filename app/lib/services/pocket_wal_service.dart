import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/pocket/pocket_models.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:path_provider/path_provider.dart';

/// Service to save Pocket MP3 recordings for backend conversion
class PocketWalService {
  /// Create a WAL file from a Pocket recording's MP3 data
  /// Saves raw MP3 file for backend conversion
  /// Returns the created WAL object
  static Future<Wal> createWalFromPocketRecording({
    required PocketRecording recording,
    required Uint8List mp3Data,
    required BtDevice device,
  }) async {
    // Parse timestamp from recording filename (format: YYYYMMDDHHMMSS)
    final timestamp = _parseTimestamp(recording.timestamp);
    final timerStart = timestamp.millisecondsSinceEpoch ~/ 1000;
    
    // Calculate duration in seconds
    final durationSeconds = recording.durationSeconds;
    
    // Save raw MP3 file (backend will convert)
    final cleanDeviceId = device.id.replaceAll(RegExp(r'[^a-zA-Z0-9]'), "").toLowerCase();
    final mp3Filename = 'audio_${cleanDeviceId}_pocket_mp3_$timerStart.mp3';
    
    debugPrint('Saving Pocket MP3 for backend conversion: $mp3Filename');
    final docsDir = await getApplicationDocumentsDirectory();
    final mp3Path = '${docsDir.path}/$mp3Filename';
    final mp3File = File(mp3Path);
    await mp3File.writeAsBytes(mp3Data);
    
    debugPrint('Saved MP3 to: $mp3Path');
    
    // Create WAL object with MP3 codec
    final wal = Wal(
      timerStart: timerStart,
      codec: BleAudioCodec.pcm8, // Use pcm8 as placeholder for MP3 (backend will handle)
      seconds: durationSeconds,
      sampleRate: 16000,
      channel: 1,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      filePath: mp3Filename, // Store only filename, not full path
      device: device.id,
      deviceModel: 'Pocket',
      storageOffset: 0,
      storageTotalBytes: mp3Data.length,
      fileNum: 1,
      totalFrames: durationSeconds * 100, // Approximate frames
      syncedFrameOffset: 0,
    );
    
    debugPrint('Created WAL for Pocket recording: ${recording.filename}, duration: ${durationSeconds}s, size: ${mp3Data.length} bytes');
    
    return wal;
  }
  
  /// Save multiple Pocket recordings as WAL files
  static Future<List<Wal>> createWalsFromPocketRecordings({
    required List<PocketRecording> recordings,
    required List<Uint8List> mp3DataList,
    required BtDevice device,
  }) async {
    if (recordings.length != mp3DataList.length) {
      throw ArgumentError('recordings and mp3DataList must have the same length');
    }
    
    final wals = <Wal>[];
    for (int i = 0; i < recordings.length; i++) {
      final wal = await createWalFromPocketRecording(
        recording: recordings[i],
        mp3Data: mp3DataList[i],
        device: device,
      );
      wals.add(wal);
    }
    
    return wals;
  }
  
  /// Add WAL files to the WAL service for syncing
  static Future<void> addWalsToService(List<Wal> wals) async {
    debugPrint('addWalsToService: Adding ${wals.length} WALs');
    
    // Load existing WALs
    final existingWals = await WalFileManager.loadWals();
    debugPrint('addWalsToService: Loaded ${existingWals.length} existing WALs');
    
    // Add new WALs (avoid duplicates by checking timerStart and device)
    final updatedWals = List<Wal>.from(existingWals);
    int addedCount = 0;
    for (final wal in wals) {
      final isDuplicate = existingWals.any(
        (existing) => existing.device == wal.device && existing.timerStart == wal.timerStart,
      );
      if (!isDuplicate) {
        updatedWals.add(wal);
        addedCount++;
        debugPrint('Added Pocket WAL: device=${wal.device}, timerStart=${wal.timerStart}, filePath=${wal.filePath}');
      } else {
        debugPrint('Skipped duplicate Pocket WAL: device=${wal.device}, timerStart=${wal.timerStart}');
      }
    }
    
    // Save updated WALs
    debugPrint('addWalsToService: Saving ${updatedWals.length} total WALs (added $addedCount new)');
    await WalFileManager.saveWals(updatedWals);
    debugPrint('addWalsToService: Successfully saved WALs');
  }
  
  /// Parse timestamp from Pocket recording format (YYYYMMDDHHMMSS)
  static DateTime _parseTimestamp(String timestamp) {
    try {
      final year = int.parse(timestamp.substring(0, 4));
      final month = int.parse(timestamp.substring(4, 6));
      final day = int.parse(timestamp.substring(6, 8));
      final hour = int.parse(timestamp.substring(8, 10));
      final minute = int.parse(timestamp.substring(10, 12));
      final second = int.parse(timestamp.substring(12, 14));
      
      return DateTime(year, month, day, hour, minute, second);
    } catch (e) {
      debugPrint('Error parsing timestamp $timestamp: $e');
      // Fallback to current time
      return DateTime.now();
    }
  }
  
}
