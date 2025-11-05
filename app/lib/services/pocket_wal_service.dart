import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/pocket/pocket_models.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/wal_file_manager.dart';
import 'package:path_provider/path_provider.dart';

/// Service to convert Pocket MP3 recordings to WAL files for processing
class PocketWalService {
  /// Create a WAL file from a Pocket recording's MP3 data
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
    
    // Save MP3 file directly - backend will handle conversion
    final directory = await getApplicationDocumentsDirectory();
    final cleanDeviceId = device.id.replaceAll(RegExp(r'[^a-zA-Z0-9]'), "").toLowerCase();
    final mp3Filename = 'pocket_${cleanDeviceId}_$timerStart.mp3';
    final filePath = '${directory.path}/$mp3Filename';
    
    final file = File(filePath);
    await file.writeAsBytes(mp3Data);
    
    debugPrint('Saved Pocket MP3: $filePath');
    
    // Create WAL object
    // Note: We use opus codec as a placeholder since the backend will handle MP3
    // The actual audio format doesn't matter for the sync process
    final wal = Wal(
      timerStart: timerStart,
      codec: BleAudioCodec.opus, // Placeholder codec
      seconds: durationSeconds,
      sampleRate: 16000, // Standard sample rate
      channel: 1, // Mono
      status: WalStatus.miss, // Mark as missing/ready to sync
      storage: WalStorage.sdcard, // Mark as external source (like SD card)
      filePath: filePath,
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
    // Load existing WALs
    final existingWals = await WalFileManager.loadWals();
    
    // Add new WALs (avoid duplicates by checking timerStart and device)
    final updatedWals = List<Wal>.from(existingWals);
    for (final wal in wals) {
      final isDuplicate = existingWals.any(
        (existing) => existing.device == wal.device && existing.timerStart == wal.timerStart,
      );
      if (!isDuplicate) {
        updatedWals.add(wal);
        debugPrint('Added Pocket WAL to service: ${wal.id}');
      } else {
        debugPrint('Skipped duplicate Pocket WAL: ${wal.id}');
      }
    }
    
    // Save updated WALs
    await WalFileManager.saveWals(updatedWals);
    debugPrint('Saved ${wals.length} Pocket WALs to service');
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
