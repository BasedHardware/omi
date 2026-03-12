import CoreBluetooth

/// BLE Service and Characteristic UUIDs for all supported devices
/// Ported from: omi/app/lib/services/devices/models.dart
enum DeviceUUIDs {

    // MARK: - Omi Device

    enum Omi {
        // Main service
        static let mainService = CBUUID(string: "19B10000-E8F2-537E-4F6C-D104768A1214")
        static let audioDataStream = CBUUID(string: "19B10001-E8F2-537E-4F6C-D104768A1214")
        static let audioCodec = CBUUID(string: "19B10002-E8F2-537E-4F6C-D104768A1214")
        static let imageDataStream = CBUUID(string: "19B10005-E8F2-537E-4F6C-D104768A1214")
        static let imageCaptureControl = CBUUID(string: "19B10006-E8F2-537E-4F6C-D104768A1214")

        // Settings service
        static let settingsService = CBUUID(string: "19B10010-E8F2-537E-4F6C-D104768A1214")
        static let settingsDimRatio = CBUUID(string: "19B10011-E8F2-537E-4F6C-D104768A1214")
        static let settingsMicGain = CBUUID(string: "19B10012-E8F2-537E-4F6C-D104768A1214")

        // Features service
        static let featuresService = CBUUID(string: "19B10020-E8F2-537E-4F6C-D104768A1214")
        static let featuresCharacteristic = CBUUID(string: "19B10021-E8F2-537E-4F6C-D104768A1214")
    }

    // MARK: - Button Service

    enum Button {
        static let service = CBUUID(string: "23BA7924-0000-1000-7450-346EAC492E92")
        static let trigger = CBUUID(string: "23BA7925-0000-1000-7450-346EAC492E92")
    }

    // MARK: - Storage Service

    enum Storage {
        static let service = CBUUID(string: "30295780-4301-EABD-2904-2849ADFEAE43")
        static let dataStream = CBUUID(string: "30295781-4301-EABD-2904-2849ADFEAE43")
        static let readControl = CBUUID(string: "30295782-4301-EABD-2904-2849ADFEAE43")
        static let wifi = CBUUID(string: "30295783-4301-EABD-2904-2849ADFEAE43")
    }

    // MARK: - Accelerometer Service

    enum Accelerometer {
        static let service = CBUUID(string: "32403790-0000-1000-7450-BF445E5829A2")
        static let dataStream = CBUUID(string: "32403791-0000-1000-7450-BF445E5829A2")
    }

    // MARK: - Battery Service (Standard BLE)

    enum Battery {
        static let service = CBUUID(string: "180F")
        static let level = CBUUID(string: "2A19")
    }

    // MARK: - Speaker/Haptic Service

    enum Speaker {
        static let service = CBUUID(string: "CAB1AB95-2EA5-4F4D-BB56-874B72CFC984")
        static let dataStream = CBUUID(string: "CAB1AB96-2EA5-4F4D-BB56-874B72CFC984")
    }

    // MARK: - Device Information Service (Standard BLE)

    enum DeviceInfo {
        static let service = CBUUID(string: "180A")
        static let modelNumber = CBUUID(string: "2A24")
        static let firmwareRevision = CBUUID(string: "2A26")
        static let hardwareRevision = CBUUID(string: "2A27")
        static let manufacturerName = CBUUID(string: "2A29")
    }

    // MARK: - Frame (Brilliant Labs)

    enum Frame {
        static let service = CBUUID(string: "7A230001-5475-A6A4-654C-8431F6AD49C4")
    }

    // MARK: - PLAUD NotePin

    enum PLAUD {
        static let service = CBUUID(string: "00001910-0000-1000-8000-00805F9B34FB")
        static let writeCharacteristic = CBUUID(string: "00002BB1-0000-1000-8000-00805F9B34FB")
        static let notifyCharacteristic = CBUUID(string: "00002BB0-0000-1000-8000-00805F9B34FB")

        /// PLAUD manufacturer ID for advertisement data detection
        static let manufacturerId: UInt16 = 93
    }

    // MARK: - Bee

    enum Bee {
        static let service = CBUUID(string: "03D5D5C4-A86C-11EE-9D89-8F2089A49E7E")
    }

    // MARK: - Fieldy (Compass)

    enum Fieldy {
        static let service = CBUUID(string: "4FAFC201-1FB5-459E-8FCC-C5C9C331914B")
    }

    // MARK: - Friend Pendant

    enum FriendPendant {
        static let service = CBUUID(string: "1A3FD0E7-B1F3-AC9E-2E49-B647B2C4F8DA")
        static let audioCharacteristic = CBUUID(string: "01000000-1111-1111-1111-111111111111")
    }

    // MARK: - Limitless Pendant

    enum Limitless {
        static let service = CBUUID(string: "632DE001-604C-446B-A80F-7963E950F3FB")
        static let txCharacteristic = CBUUID(string: "632DE002-604C-446B-A80F-7963E950F3FB")
        static let rxCharacteristic = CBUUID(string: "632DE003-604C-446B-A80F-7963E950F3FB")
    }

    // MARK: - Helper Methods

    /// All service UUIDs that indicate a supported device during scanning
    static var allSupportedServiceUUIDs: [CBUUID] {
        [
            Omi.mainService,
            Frame.service,
            PLAUD.service,
            Bee.service,
            Fieldy.service,
            FriendPendant.service,
            Limitless.service
        ]
    }
}
