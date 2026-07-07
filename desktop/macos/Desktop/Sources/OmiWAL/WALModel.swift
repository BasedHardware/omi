import Foundation

// MARK: - WAL Status

/// Status of a Write-Ahead Log entry
/// Ported from: omi/app/lib/services/wals/wal_service.dart
package enum WALStatus: String, Codable {
    case inProgress = "inProgress"  // Currently recording/receiving
    case miss = "miss"              // Downloaded from device, needs upload
    case uploaded = "uploaded"      // Server ack (202); reconciler resolves to synced
    case synced = "synced"          // Successfully uploaded to cloud
    case corrupted = "corrupted"    // Failed to process
}

// MARK: - WAL Storage Type

/// Storage location of a WAL entry
package enum WALStorageType: String, Codable {
    case memory = "mem"         // In-memory buffer
    case disk = "disk"          // Local disk file
    case sdcard = "sdcard"      // Device SD card
    case flashPage = "flashPage" // Device flash memory (Limitless)
}

// MARK: - WAL Entry

/// A Write-Ahead Log entry representing an audio recording chunk
/// Ported from: omi/app/lib/services/wals/wal_service.dart
package struct WALEntry: Codable, Identifiable {
    /// Unique identifier (format: {deviceId}_{timerStart})
    package var id: String { "\(device)_\(timerStart)" }

    /// Unix timestamp when recording started
    package var timerStart: Int

    /// Audio codec used
    package var codec: String

    /// Number of audio channels (typically 1 for mono)
    package var channel: Int

    /// Sample rate in Hz (typically 16000)
    package var sampleRate: Int

    /// Current sync status
    package var status: WALStatus

    /// Where the audio data is stored
    package var storage: WALStorageType

    /// Filename (resolved at runtime to full path)
    package var filePath: String?

    /// Duration in seconds
    package var seconds: Int

    /// Device identifier
    package var device: String

    /// Device model name
    package var deviceModel: String

    /// For SD card: current byte offset in device storage
    package var storageOffset: Int

    /// For SD card: total bytes on device
    package var storageTotalBytes: Int

    /// File number on device (typically 1)
    package var fileNum: Int

    /// Total frames in this WAL
    package var totalFrames: Int

    /// Number of frames already synced to cloud
    package var syncedFrameOffset: Int

    /// Original storage location (for migration tracking)
    package var originalStorage: WALStorageType?

    /// Server job id after HTTP 202 upload ack (reconciler polls this)
    package var jobId: String?

    /// Unix timestamp when upload was acknowledged (HTTP 202)
    package var uploadedAt: Int

    // MARK: - Initialization

    package init(
        timerStart: Int,
        codec: String,
        channel: Int = 1,
        sampleRate: Int = 16000,
        status: WALStatus = .inProgress,
        storage: WALStorageType = .memory,
        filePath: String? = nil,
        seconds: Int = 60,
        device: String,
        deviceModel: String,
        storageOffset: Int = 0,
        storageTotalBytes: Int = 0,
        fileNum: Int = 1,
        totalFrames: Int = 0,
        syncedFrameOffset: Int = 0,
        originalStorage: WALStorageType? = nil,
        jobId: String? = nil,
        uploadedAt: Int = 0
    ) {
        self.timerStart = timerStart
        self.codec = codec
        self.channel = channel
        self.sampleRate = sampleRate
        self.status = status
        self.storage = storage
        self.filePath = filePath
        self.seconds = seconds
        self.device = device
        self.deviceModel = deviceModel
        self.storageOffset = storageOffset
        self.storageTotalBytes = storageTotalBytes
        self.fileNum = fileNum
        self.totalFrames = totalFrames
        self.syncedFrameOffset = syncedFrameOffset
        self.originalStorage = originalStorage
        self.jobId = jobId
        self.uploadedAt = uploadedAt
    }

    package enum CodingKeys: String, CodingKey {
        case timerStart, codec, channel, sampleRate, status, storage, filePath, seconds
        case device, deviceModel, storageOffset, storageTotalBytes, fileNum, totalFrames
        case syncedFrameOffset, originalStorage, jobId, uploadedAt
    }

    package init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        timerStart = try container.decode(Int.self, forKey: .timerStart)
        codec = try container.decode(String.self, forKey: .codec)
        channel = try container.decodeIfPresent(Int.self, forKey: .channel) ?? 1
        sampleRate = try container.decodeIfPresent(Int.self, forKey: .sampleRate) ?? 16000
        status = try container.decode(WALStatus.self, forKey: .status)
        storage = try container.decode(WALStorageType.self, forKey: .storage)
        filePath = try container.decodeIfPresent(String.self, forKey: .filePath)
        seconds = try container.decode(Int.self, forKey: .seconds)
        device = try container.decode(String.self, forKey: .device)
        deviceModel = try container.decode(String.self, forKey: .deviceModel)
        storageOffset = try container.decodeIfPresent(Int.self, forKey: .storageOffset) ?? 0
        storageTotalBytes = try container.decodeIfPresent(Int.self, forKey: .storageTotalBytes) ?? 0
        fileNum = try container.decodeIfPresent(Int.self, forKey: .fileNum) ?? 1
        totalFrames = try container.decodeIfPresent(Int.self, forKey: .totalFrames) ?? 0
        syncedFrameOffset = try container.decodeIfPresent(Int.self, forKey: .syncedFrameOffset) ?? 0
        originalStorage = try container.decodeIfPresent(WALStorageType.self, forKey: .originalStorage)
        jobId = try container.decodeIfPresent(String.self, forKey: .jobId)
        uploadedAt = try container.decodeIfPresent(Int.self, forKey: .uploadedAt) ?? 0
    }

    package func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(timerStart, forKey: .timerStart)
        try container.encode(codec, forKey: .codec)
        try container.encode(channel, forKey: .channel)
        try container.encode(sampleRate, forKey: .sampleRate)
        try container.encode(status, forKey: .status)
        try container.encode(storage, forKey: .storage)
        try container.encodeIfPresent(filePath, forKey: .filePath)
        try container.encode(seconds, forKey: .seconds)
        try container.encode(device, forKey: .device)
        try container.encode(deviceModel, forKey: .deviceModel)
        try container.encode(storageOffset, forKey: .storageOffset)
        try container.encode(storageTotalBytes, forKey: .storageTotalBytes)
        try container.encode(fileNum, forKey: .fileNum)
        try container.encode(totalFrames, forKey: .totalFrames)
        try container.encode(syncedFrameOffset, forKey: .syncedFrameOffset)
        try container.encodeIfPresent(originalStorage, forKey: .originalStorage)
        try container.encodeIfPresent(jobId, forKey: .jobId)
        if uploadedAt != 0 {
            try container.encode(uploadedAt, forKey: .uploadedAt)
        }
    }

    // MARK: - Computed Properties

    /// Frames per second based on codec
    package var framesPerSecond: Int {
        switch codec {
        case "opus": return 100
        case "opus_fs320": return 50
        default: return 100
        }
    }

    /// Bytes per frame based on codec
    package var bytesPerFrame: Int {
        switch codec {
        case "opus": return 80
        case "opus_fs320": return 160
        default: return 80
        }
    }

    /// Opus decoder frame size in samples — the `_fsN` token the backend parses
    /// from the filename (`decode_files_to_wav` → `frame_size`). Must be sample
    /// count, not byte length, or audio decodes with half-sized buffers.
    /// Flutter writes `_fs160` (opus) / `_fs320` (opus_fs320).
    package var samplesPerFrame: Int {
        guard framesPerSecond > 0 else { return 160 }
        return sampleRate / framesPerSecond
    }

    /// Expected total frames for the duration
    package var expectedFrames: Int {
        framesPerSecond * seconds
    }

    /// Bytes remaining to download from device
    package var bytesRemaining: Int {
        max(0, storageTotalBytes - storageOffset)
    }

    /// Whether this WAL is complete (all frames received)
    package var isComplete: Bool {
        totalFrames >= expectedFrames || status == .synced
    }

    /// Generate filename for this WAL. The `_fsN` token is the Opus decoder
    /// frame size in samples (matching Flutter), not the encoded byte length.
    package func generateFileName() -> String {
        "audio_\(device)_\(codec)_\(sampleRate)_\(channel)_fs\(samplesPerFrame)_\(timerStart).bin"
    }
}

// MARK: - Sync upload filename normalization

/// Helpers for `/v2/sync-local-files` multipart uploads.
package enum WALSyncUploadFileName {
    private static let fsTokenPattern = "_fs(\\d+)_(\\d+)\\.bin$"

    /// Rewrites legacy desktop `_fsN` tokens that used encoded byte length
    /// (`_fs80` for opus, `_fs160` for opus_fs320) to sample-frame size
    /// (`_fs160`/`_fs320`) expected by the backend decoder.
    package static func normalizedForUpload(_ fileName: String) -> String {
        guard fileName.hasPrefix("audio_"), fileName.hasSuffix(".bin") else {
            return fileName
        }
        if fileName.contains("_pcm16_") || fileName.contains("_pcm8_") {
            return fileName
        }

        guard let fsRange = fileName.range(of: fsTokenPattern, options: .regularExpression) else {
            return fileName
        }
        let fsTokenMatch = String(fileName[fsRange])
        guard
            let fsValueRange = fsTokenMatch.range(of: "_fs(\\d+)_", options: .regularExpression),
            let fsValue = Int(fsTokenMatch[fsValueRange].dropFirst(3).dropLast(1))
        else {
            return fileName
        }
        let fsToken = "_fs\(fsValue)"

        let codec: String
        if fileName.contains("_opus_fs320_") {
            codec = "opus_fs320"
        } else if fileName.contains("_opus_") {
            codec = "opus"
        } else {
            return fileName
        }

        let reference = WALEntry(timerStart: 0, codec: codec, device: "x", deviceModel: "x")
        let expectedSamples = reference.samplesPerFrame
        guard fsValue == reference.bytesPerFrame else {
            return fileName
        }
        return fileName.replacingOccurrences(of: fsToken, with: "_fs\(expectedSamples)")
    }
}

// MARK: - WAL Metadata

/// Metadata wrapper for WAL storage file
package struct WALMetadata: Codable {
    /// Schema version for migration
    package var version: Int = 1

    /// Timestamp of last save (milliseconds)
    package var timestamp: Int64

    /// All WAL entries
    package var wals: [WALEntry]

    package init(wals: [WALEntry]) {
        self.timestamp = Int64(Date().timeIntervalSince1970 * 1000)
        self.wals = wals
    }
}

// MARK: - Storage Read Command

/// Commands for device storage operations
package enum StorageCommand: Int {
    case read = 0x00   // Start reading from offset
    case clear = 0x01  // Clear SD card storage
}

// MARK: - Storage Response

/// Response codes from storage data stream
package enum StorageResponse: UInt8 {
    case ok = 0x00            // Success
    case badFileSize = 0x03   // Invalid file size
    case fileSizeZero = 0x04  // File is empty
    case endOfTransmission = 0x64  // Transfer complete (100)

    package var isSuccess: Bool {
        self == .ok
    }

    package var isError: Bool {
        self != .ok && self != .endOfTransmission
    }
}

// MARK: - Frame Validation

/// Valid Opus TOC bytes for frame validation
package enum OpusFrameValidator {
    package static let validTocBytes: Set<UInt8> = [0xb8, 0xb0, 0xbc, 0xf8, 0xfc, 0x78, 0x7c]

    /// Check if a byte is a valid Opus TOC byte
    package static func isValidTocByte(_ byte: UInt8) -> Bool {
        validTocBytes.contains(byte)
    }

    /// Check if data starts with a valid Opus frame
    package static func startsWithValidFrame(_ data: Data) -> Bool {
        guard !data.isEmpty else { return false }
        return isValidTocByte(data[0])
    }
}

// MARK: - WiFi Sync Status

/// WiFi sync status codes from device
/// Ported from: omi/app/lib/services/devices/wifi_sync_error.dart
package enum WifiStatus: Int {
    case off = 0          // WiFi disabled
    case shutdown = 1     // Shutting down
    case on = 2           // WiFi on
    case connecting = 3   // Connecting to network
    case connected = 4    // Connected to network
    case tcpConnected = 5 // TCP connection established

    package var displayName: String {
        switch self {
        case .off: return "Off"
        case .shutdown: return "Shutting down"
        case .on: return "Starting"
        case .connecting: return "Connecting"
        case .connected: return "Connected"
        case .tcpConnected: return "Transferring"
        }
    }

    package var isActive: Bool {
        self == .connected || self == .tcpConnected
    }
}

// MARK: - Sync Progress

/// Progress tracking for sync operations
package struct SyncProgress {
    package var totalBytes: Int
    package var downloadedBytes: Int
    package var framesDownloaded: Int
    package var bytesPerSecond: Double
    package var estimatedSecondsRemaining: Double?

    package var percentComplete: Double {
        guard totalBytes > 0 else { return 0 }
        return Double(downloadedBytes) / Double(totalBytes) * 100
    }

    package init(totalBytes: Int = 0, downloadedBytes: Int = 0, framesDownloaded: Int = 0, bytesPerSecond: Double = 0) {
        self.totalBytes = totalBytes
        self.downloadedBytes = downloadedBytes
        self.framesDownloaded = framesDownloaded
        self.bytesPerSecond = bytesPerSecond

        if bytesPerSecond > 0 {
            let remaining = Double(totalBytes - downloadedBytes)
            self.estimatedSecondsRemaining = remaining / bytesPerSecond
        }
    }
}
