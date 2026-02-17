import Foundation

// MARK: - Omi Feature Flags

/// Feature flags for Omi device capabilities
/// Must match the firmware definitions in features.h
/// Ported from: omi/app/lib/services/devices.dart
struct OmiFeatures: OptionSet {
    let rawValue: Int

    static let speaker        = OmiFeatures(rawValue: 1 << 0)
    static let accelerometer  = OmiFeatures(rawValue: 1 << 1)
    static let button         = OmiFeatures(rawValue: 1 << 2)
    static let battery        = OmiFeatures(rawValue: 1 << 3)
    static let usb            = OmiFeatures(rawValue: 1 << 4)
    static let haptic         = OmiFeatures(rawValue: 1 << 5)
    static let offlineStorage = OmiFeatures(rawValue: 1 << 6)
    static let ledDimming     = OmiFeatures(rawValue: 1 << 7)
    static let micGain        = OmiFeatures(rawValue: 1 << 8)
    static let wifi           = OmiFeatures(rawValue: 1 << 9)

    /// All features combined
    static let all: OmiFeatures = [
        .speaker, .accelerometer, .button, .battery, .usb,
        .haptic, .offlineStorage, .ledDimming, .micGain, .wifi
    ]
}

// MARK: - Image Orientation (OpenGlass)

/// Image orientation for OpenGlass camera
/// Ported from: omi/app/lib/backend/schema/bt_device/bt_device.dart
enum ImageOrientation: Int, CaseIterable {
    case orientation0 = 0    // 0 degrees
    case orientation90 = 1   // 90 degrees clockwise
    case orientation180 = 2  // 180 degrees
    case orientation270 = 3  // 270 degrees clockwise

    /// Create from raw value with fallback to 0 degrees
    static func from(value: Int) -> ImageOrientation {
        ImageOrientation(rawValue: value) ?? .orientation0
    }

    /// Rotation angle in degrees
    var degrees: Int {
        rawValue * 90
    }
}

// MARK: - Device Type

/// Supported BLE device types
/// Ported from: omi/app/lib/backend/schema/bt_device/bt_device.dart
enum DeviceType: String, CaseIterable, Codable {
    case omi
    case openglass
    case frame
    case appleWatch
    case plaud
    case bee
    case fieldy
    case friendPendant
    case limitless

    /// Human-readable display name
    var displayName: String {
        switch self {
        case .omi: return "Omi"
        case .openglass: return "OpenGlass"
        case .frame: return "Frame"
        case .appleWatch: return "Apple Watch"
        case .plaud: return "PLAUD"
        case .bee: return "Bee"
        case .fieldy: return "Fieldy"
        case .friendPendant: return "Friend Pendant"
        case .limitless: return "Limitless"
        }
    }

    /// Manufacturer name for this device type
    var manufacturerName: String {
        switch self {
        case .omi, .openglass: return "Based Hardware"
        case .frame: return "Brilliant Labs"
        case .appleWatch: return "Apple"
        case .plaud: return "PLAUD"
        case .bee: return "Bee"
        case .fieldy: return "Fieldy"
        case .friendPendant: return "Friend"
        case .limitless: return "Limitless"
        }
    }

    /// Default hardware revision when not available from device
    var defaultHardwareRevision: String {
        switch self {
        case .omi: return "Seeed Xiao BLE Sense"
        case .openglass: return "Seeed Xiao BLE Sense"
        case .frame: return "Brilliant Labs Frame"
        case .appleWatch: return "Unknown"
        case .plaud: return "1.0.0"
        case .bee: return "1.0.0"
        case .fieldy: return "Fieldy Hardware"
        case .friendPendant: return "1.0.0"
        case .limitless: return "Unknown"
        }
    }

    /// Default firmware revision when not available from device
    var defaultFirmwareRevision: String {
        switch self {
        case .omi, .openglass: return "1.0.2"
        default: return "1.0.0"
        }
    }

    /// Whether this device type requires a firmware compatibility warning
    var requiresFirmwareWarning: Bool {
        switch self {
        case .plaud, .bee, .fieldy, .friendPendant, .limitless:
            return true
        case .omi, .openglass, .frame, .appleWatch:
            return false
        }
    }

    /// Firmware warning message for third-party devices
    var firmwareWarningMessage: String? {
        guard requiresFirmwareWarning else { return nil }

        let appName: String
        switch self {
        case .plaud: appName = "PLAUD"
        case .bee: appName = "Bee"
        case .fieldy: appName = "Compass"
        case .friendPendant: appName = "Friend"
        case .limitless: appName = "Limitless"
        default: return nil
        }

        return """
        Your device's current firmware works great with Omi.

        We recommend keeping your current firmware and not updating through the \(appName) app, as newer versions may affect compatibility.
        """
    }

    /// SF Symbol icon name for this device type
    var iconName: String {
        switch self {
        case .omi, .openglass:
            return "wave.3.right.circle.fill"
        case .frame:
            return "eyeglasses"
        case .appleWatch:
            return "applewatch"
        case .plaud:
            return "waveform.circle.fill"
        case .bee:
            return "antenna.radiowaves.left.and.right.circle.fill"
        case .fieldy:
            return "circle.dotted"
        case .friendPendant:
            return "person.wave.2.fill"
        case .limitless:
            return "infinity.circle.fill"
        }
    }
}

// MARK: - Audio Codec Support

/// BLE audio codecs supported by devices
/// Ported from: omi/app/lib/backend/schema/bt_device/bt_device.dart
enum BleAudioCodec: Int, CaseIterable, Codable {
    case pcm16 = 0      // PCM 16-bit @ 16kHz
    case pcm8 = 1       // PCM 8-bit @ 16kHz
    case mulaw16 = 10   // µ-law 16-bit
    case mulaw8 = 11    // µ-law 8-bit
    case opus = 20      // OPUS @ 16kHz
    case opusFS320 = 21 // OPUS with 320 sample frames (50fps)
    case aac = 22       // AAC
    case lc3FS1030 = 23 // LC3 @ 10ms/30 bytes per frame
    case unknown = -1

    /// Codec name for API/logging
    var name: String {
        switch self {
        case .pcm16: return "pcm16"
        case .pcm8: return "pcm8"
        case .mulaw16: return "mulaw16"
        case .mulaw8: return "mulaw8"
        case .opus: return "opus"
        case .opusFS320: return "opus_fs320"
        case .aac: return "aac"
        case .lc3FS1030: return "lc3_fs1030"
        case .unknown: return "unknown"
        }
    }

    /// Human-readable display name
    var displayName: String {
        switch self {
        case .pcm16: return "PCM (16kHz)"
        case .pcm8: return "PCM (8kHz)"
        case .mulaw16: return "µ-law (16-bit)"
        case .mulaw8: return "µ-law (8-bit)"
        case .opus: return "OPUS"
        case .opusFS320: return "OPUS (320)"
        case .aac: return "AAC"
        case .lc3FS1030: return "LC3 (10ms/30B)"
        case .unknown: return "Unknown"
        }
    }

    /// Alias for LC3 codec (for code clarity)
    static var lc3: BleAudioCodec { .lc3FS1030 }

    /// Check if this is an Opus-based codec
    var isOpus: Bool {
        self == .opus || self == .opusFS320
    }

    /// Check if this is a PCM-based codec (no decoding needed)
    var isPCM: Bool {
        self == .pcm8 || self == .pcm16
    }

    /// Sample rate in Hz
    var sampleRate: Int { 16000 }

    /// Bit depth
    var bitDepth: Int {
        switch self {
        case .pcm8, .mulaw8: return 8
        default: return 16
        }
    }

    /// Frames per second
    var framesPerSecond: Int {
        self == .opusFS320 ? 50 : 100
    }

    /// Frame length in bytes
    var frameLengthInBytes: Int {
        self == .opusFS320 ? 160 : 80
    }

    /// PDM frame size
    var frameSize: Int {
        self == .opusFS320 ? 320 : 160
    }

    /// Whether OPUS is supported
    var isOpusSupported: Bool {
        self == .opus || self == .opusFS320
    }

    /// Whether this codec is supported for custom STT providers
    var isCustomSttSupported: Bool {
        switch self {
        case .pcm8, .pcm16, .opus, .opusFS320:
            return true
        default:
            return false
        }
    }

    /// Create codec from name string
    static func from(name: String) -> BleAudioCodec {
        switch name.lowercased() {
        case "pcm16": return .pcm16
        case "pcm8": return .pcm8
        case "mulaw16": return .mulaw16
        case "mulaw8": return .mulaw8
        case "opus": return .opus
        case "opus_fs320": return .opusFS320
        case "aac": return .aac
        case "lc3_fs1030": return .lc3FS1030
        default: return .unknown
        }
    }
}
