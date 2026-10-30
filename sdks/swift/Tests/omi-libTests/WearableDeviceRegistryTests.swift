import XCTest
import CoreBluetooth
@testable import omi_lib

class WearableDeviceRegistryTests: XCTestCase {
    func testRegisterDeviceDuplicateUUID() {
        let registry = WearableDeviceRegistry.shared
        // Assuming Friend is available and conforms to WearableDevice
        do {
            try registry.registerDevice(wearable: Friend.self)
        } catch {
            XCTFail("Should not throw on first registration")
        }

        do {
            try registry.registerDevice(wearable: Friend.self)
            XCTFail("Should throw on second registration with same UUID")
        } catch let error as WearableDeviceRegistry.RegistryError {
            XCTAssertEqual(error, .duplicateScanUUID)
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }
}
