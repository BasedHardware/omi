import 'dart:typed_data';

/// Represents a recording stored on the Pocket device
/// Port of Python Recording model from pocket/models.py
class PocketRecording {
  final String directory;
  final String timestamp;
  final int packets;
  final DateTime? datetime;

  PocketRecording({
    required this.directory,
    required this.timestamp,
    required this.packets,
    this.datetime,
  });

  String get filename => '${directory}_$timestamp.mp3';
  
  String get recordingId => '${directory}_$timestamp';

  /// Duration in seconds (estimated from packets)
  int get durationSeconds => packets;

  /// Display name for UI
  String get displayName {
    if (datetime != null) {
      return '${datetime!.month}/${datetime!.day} ${datetime!.hour}:${datetime!.minute.toString().padLeft(2, '0')}';
    }
    return timestamp;
  }

  /// Duration display string (MM:SS)
  String get durationDisplay {
    final minutes = durationSeconds ~/ 60;
    final seconds = durationSeconds % 60;
    return '$minutes:${seconds.toString().padLeft(2, '0')}';
  }

  factory PocketRecording.fromResponse(String directory, String timestamp, int packets) {
    // Try to parse timestamp to datetime
    // Format: YYYYMMDDHHmmss (e.g., 20251101143022)
    DateTime? dt;
    try {
      if (timestamp.length == 14) {
        final year = int.parse(timestamp.substring(0, 4));
        final month = int.parse(timestamp.substring(4, 6));
        final day = int.parse(timestamp.substring(6, 8));
        final hour = int.parse(timestamp.substring(8, 10));
        final minute = int.parse(timestamp.substring(10, 12));
        final second = int.parse(timestamp.substring(12, 14));
        dt = DateTime(year, month, day, hour, minute, second);
      }
    } catch (e) {
      // If parsing fails, datetime remains null
    }

    return PocketRecording(
      directory: directory,
      timestamp: timestamp,
      packets: packets,
      datetime: dt,
    );
  }

  @override
  String toString() {
    return 'PocketRecording(directory: $directory, timestamp: $timestamp, packets: $packets)';
  }
}

/// Represents device information from Pocket device
/// Port of Python DeviceInfo model from pocket/models.py
class PocketDeviceInfo {
  final String? firmware;
  final int? battery;
  final int? storageUsed;
  final int? storageTotal;

  PocketDeviceInfo({
    this.firmware,
    this.battery,
    this.storageUsed,
    this.storageTotal,
  });

  /// Storage used percentage
  double? get storageUsedPercent {
    if (storageUsed != null && storageTotal != null && storageTotal! > 0) {
      return (storageUsed! / storageTotal!) * 100;
    }
    return null;
  }

  /// Storage used in MB
  double? get storageUsedMB {
    if (storageUsed != null) {
      return storageUsed! / 1024 / 1024;
    }
    return null;
  }

  /// Storage total in MB
  double? get storageTotalMB {
    if (storageTotal != null) {
      return storageTotal! / 1024 / 1024;
    }
    return null;
  }

  @override
  String toString() {
    return 'PocketDeviceInfo(firmware: $firmware, battery: $battery%, storage: ${storageUsedMB?.toStringAsFixed(1)}MB/${storageTotalMB?.toStringAsFixed(1)}MB)';
  }
}

/// Represents the download progress of a recording
class PocketDownloadProgress {
  final String recordingId;
  final int totalBytes;
  final int downloadedBytes;
  final Uint8List data;

  PocketDownloadProgress({
    required this.recordingId,
    required this.totalBytes,
    required this.downloadedBytes,
    required this.data,
  });

  double get progress {
    if (totalBytes == 0) return 0.0;
    return downloadedBytes / totalBytes;
  }

  bool get isComplete => downloadedBytes >= totalBytes;

  @override
  String toString() {
    return 'PocketDownloadProgress(${(progress * 100).toStringAsFixed(1)}%, $downloadedBytes/$totalBytes bytes)';
  }
}
