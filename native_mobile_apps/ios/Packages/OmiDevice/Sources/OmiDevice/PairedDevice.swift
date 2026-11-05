import Foundation

/// The paired wearable, encoded exactly like the Flutter app's `btDevice` preference
/// (`app/lib/backend/schema/bt_device/bt_device.dart:724-739`) so pairing survives the update.
public struct PairedDevice: Codable, Hashable, Sendable {
    public var id: String
    public var name: String
    public var type: String
    public var rssi: Int
    public var modelNumber: String?
    public var firmwareRevision: String?
    public var hardwareRevision: String?
    public var manufacturerName: String?
    /// The per-unit id from Device Information (CV1 and later), when the firmware reports one.
    public var serialNumber: String?

    public init(id: String, name: String, type: String = "omi", rssi: Int = 0) {
        self.id = id
        self.name = name
        self.type = type
        self.rssi = rssi
    }

    public static func decode(_ json: String?) -> PairedDevice? {
        guard let data = json?.data(using: .utf8), !data.isEmpty else { return nil }
        guard let device = try? JSONDecoder().decode(PairedDevice.self, from: data), !device.id.isEmpty else { return nil }
        return device
    }

    public var encoded: String? {
        (try? JSONEncoder().encode(self)).flatMap { String(data: $0, encoding: .utf8) }
    }
}
