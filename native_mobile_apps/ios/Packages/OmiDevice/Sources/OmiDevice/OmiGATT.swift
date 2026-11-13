@preconcurrency import CoreBluetooth
import Foundation

/// The Omi wearable's GATT profile. Source: upstream `app/lib/services/devices/models.dart`,
/// `connectors/omi_connection.dart`, firmware `omi/firmware/omi/src/lib/core/config.h`.
public enum OmiGATT {
    public static let audioService = CBUUID(string: "19b10000-e8f2-537e-4f6c-d104768a1214")
    public static let audioData = CBUUID(string: "19b10001-e8f2-537e-4f6c-d104768a1214")
    public static let audioCodec = CBUUID(string: "19b10002-e8f2-537e-4f6c-d104768a1214")
    public static let buttonService = CBUUID(string: "23ba7924-0000-1000-7450-346eac492e92")
    public static let buttonData = CBUUID(string: "23ba7925-0000-1000-7450-346eac492e92")
    public static let batteryService = CBUUID(string: "180F")
    public static let batteryLevel = CBUUID(string: "2A19")
    public static let deviceInfoService = CBUUID(string: "180A")
    public static let modelNumber = CBUUID(string: "2A24")
    public static let firmwareRevision = CBUUID(string: "2A26")
    public static let hardwareRevision = CBUUID(string: "2A27")
    public static let manufacturerName = CBUUID(string: "2A29")

    /// CoreBluetooth state restoration id the Flutter build used; keeping it lets iOS hand a
    /// still-connected Omi back to the native app after the update (same bundle id).
    public static let restoreIdentifier = "com.omi.ble.restore"

    /// MCUmgr's SMP service (firmware updates). `McuFirmwareUpdater` speaks it, not this driver.
    public static let smpService = CBUUID(string: "8D53DC1D-1DB7-4CD3-868B-8A527460AA84")

    /// Codec ids from the codec characteristic (`omi_connection.dart:416-438`).
    public enum Codec: Int, Sendable {
        case pcm16 = 0
        case pcm8 = 1
        case opus = 20
        case opusFS320 = 21

        /// The `/v4/listen` `codec` query value.
        public var listenValue: String {
            switch self {
            case .pcm16: "pcm16"
            case .pcm8: "pcm8"
            case .opus: "opus"
            case .opusFS320: "opus_fs320"
            }
        }

        public var sampleRate: Int {
            self == .pcm8 ? 8000 : 16000
        }
    }

    /// Button notifications: a little-endian `int` state (firmware `core/button.c`). A long press
    /// powers the Omi off in firmware; press/release only matter for push-to-talk.
    public enum ButtonEvent: UInt32, Sendable {
        case singleTap = 1
        case doubleTap = 2
        case longPress = 3
        case press = 4
        case release = 5

        public init?(_ value: Data) {
            guard value.count >= 4 else { return nil }
            let raw = value.prefix(4).reversed().reduce(UInt32(0)) { $0 << 8 | UInt32($1) }
            self.init(rawValue: raw)
        }
    }

    /// Audio notifications carry `[id_lo, id_hi, sub_index]` then the codec payload.
    public static func audioPayload(_ packet: Data) -> (packetID: UInt16, payload: Data)? {
        guard packet.count > 3 else { return nil }
        let bytes = [UInt8](packet.prefix(3))
        let id = UInt16(bytes[0]) | (UInt16(bytes[1]) << 8)
        return (id, packet.dropFirst(3))
    }

    /// Whether an advertisement is an Omi-family wearable.
    public static func isOmi(name: String?, advertisedServices: [CBUUID]) -> Bool {
        if advertisedServices.contains(audioService) { return true }
        guard let name = name?.lowercased() else { return false }
        return name.contains("omi") || name.contains("friend")
    }
}
