import Foundation

// MARK: - WAL Status

/// Status of a Write-Ahead Log entry
/// Ported from: omi/app/lib/services/wals/wal_service.dart
enum WALStatus: String, Codable {
    case inProgress = "inProgress"  // Currently recording/receiving
    case miss = "miss"              // Downloaded from device, needs upload
    case synced = "synced"          // Successfully uploaded to cloud
    case corrupted = "corrupted"    // Failed to process
}

// MARK: - WAL Storage Type

/// Storage location of a WAL entry
enum WALStorageType: String, Codable {
    case memory = "mem"         // In-memory buffer
    case disk = "disk"          // Local disk file
    case sdcard = "sdcard"      // Device SD card
    case flashPage = "flashPage" // Device flash memory (Limitless)
}

// MARK: - WAL Entry

/// A Write-Ahead Log entry representing an audio recording chunk
/// Ported from: omi/app/lib/services/wals/wal_service.dart
struct WALEntry: Codable, Identifiable {
    /// Unique identifier (format: {deviceId}_{timerStart})
    var id: String { "\(device)_\(timerStart)" }

    /// Unix timestamp when recording started
    var timerStart: Int

    /// Audio codec used
    var codec: String

    /// Number of audio channels (typically 1 for mono)
    var channel: Int

    /// Sample rate in Hz (typically 16000)
    var sampleRate: Int

    /// Current sync status
    var status: WALStatus

    /// Where the audio data is stored
    var storage: WALStorageType

    /// Filename (resolved at runtime to full path)
    var filePath: String?

    /// Duration in seconds
    var seconds: Int

    /// Device identifier
    var device: String

    /// Device model name
    var deviceModel: String

    /// For SD card: current byte offset in device storage
    var storageOffset: Int

    /// For SD card: total bytes on device
    var storageTotalBytes: Int

    /// File number on device (typically 1)
    var fileNum: Int

    /// Total frames in this WAL
    var totalFrames: Int

    /// Number of frames already synced to cloud
    var syncedFrameOffset: Int

    /// Original storage location (for migration tracking)
    var originalStorage: WALStorageType?

    // MARK: - Initialization

    init(
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
        originalStorage: WALStorageType? = nil
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
    }

    // MARK: - Computed Properties

    /// Frames per second based on codec
    var framesPerSecond: Int {
        switch codec {
        case "opus": return 100
        case "opus_fs320": return 50
        default: return 100
        }
    }

    /// Bytes per frame based on codec
    var bytesPerFrame: Int {
        switch codec {
        case "opus": return 80
        case "opus_fs320": return 160
        default: return 80
        }
    }

    /// Expected total frames for the duration
    var expectedFrames: Int {
        framesPerSecond * seconds
    }

    /// Bytes remaining to download from device
    var bytesRemaining: Int {
        max(0, storageTotalBytes - storageOffset)
    }

    /// Whether this WAL is complete (all frames received)
    var isComplete: Bool {
        totalFrames >= expectedFrames || status == .synced
    }

    /// Generate filename for this WAL
    func generateFileName() -> String {
        "audio_\(device)_\(codec)_\(sampleRate)_\(channel)_fs\(bytesPerFrame)_\(timerStart).bin"
    }
}

// MARK: - WAL Metadata

/// Metadata wrapper for WAL storage file
struct WALMetadata: Codable {
    /// Schema version for migration
    var version: Int = 1

    /// Timestamp of last save (milliseconds)
    var timestamp: Int64

    /// All WAL entries
    var wals: [WALEntry]

    init(wals: [WALEntry]) {
        self.timestamp = Int64(Date().timeIntervalSince1970 * 1000)
        self.wals = wals
    }
}

// MARK: - Storage Read Command

/// Commands for device storage operations
enum StorageCommand: Int {
    case read = 0x00   // Start reading from offset
    case clear = 0x01  // Clear SD card storage
}

// MARK: - Storage Response

/// Response codes from storage data stream
enum StorageResponse: UInt8 {
    case ok = 0x00            // Success
    case badFileSize = 0x03   // Invalid file size
    case fileSizeZero = 0x04  // File is empty
    case endOfTransmission = 0x64  // Transfer complete (100)

    var isSuccess: Bool {
        self == .ok
    }

    var isError: Bool {
        self != .ok && self != .endOfTransmission
    }
}

// MARK: - Frame Validation

/// Valid Opus TOC bytes for frame validation
enum OpusFrameValidator {
    static let validTocBytes: Set<UInt8> = [0xb8, 0xb0, 0xbc, 0xf8, 0xfc, 0x78, 0x7c]

    /// Check if a byte is a valid Opus TOC byte
    static func isValidTocByte(_ byte: UInt8) -> Bool {
        validTocBytes.contains(byte)
    }

    /// Check if data starts with a valid Opus frame
    static func startsWithValidFrame(_ data: Data) -> Bool {
        guard !data.isEmpty else { return false }
        return isValidTocByte(data[0])
    }
}

// MARK: - WiFi Sync Status

/// WiFi sync status codes from device
/// Ported from: omi/app/lib/services/devices/wifi_sync_error.dart
enum WifiStatus: Int {
    case off = 0          // WiFi disabled
    case shutdown = 1     // Shutting down
    case on = 2           // WiFi on
    case connecting = 3   // Connecting to network
    case connected = 4    // Connected to network
    case tcpConnected = 5 // TCP connection established

    var displayName: String {
        switch self {
        case .off: return "Off"
        case .shutdown: return "Shutting down"
        case .on: return "Starting"
        case .connecting: return "Connecting"
        case .connected: return "Connected"
        case .tcpConnected: return "Transferring"
        }
    }

    var isActive: Bool {
        self == .connected || self == .tcpConnected
    }
}

// MARK: - Sync Progress

/// Progress tracking for sync operations
struct SyncProgress {
    var totalBytes: Int
    var downloadedBytes: Int
    var framesDownloaded: Int
    var bytesPerSecond: Double
    var estimatedSecondsRemaining: Double?

    var percentComplete: Double {
        guard totalBytes > 0 else { return 0 }
        return Double(downloadedBytes) / Double(totalBytes) * 100
    }

    init(totalBytes: Int = 0, downloadedBytes: Int = 0, framesDownloaded: Int = 0, bytesPerSecond: Double = 0) {
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
