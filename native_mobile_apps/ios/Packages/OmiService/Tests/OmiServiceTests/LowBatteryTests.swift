import Foundation
import OmiDevice
import OmiPersistence
@testable import OmiService
import Testing

struct LowBatteryAlertTests {
    @Test func notifiesOncePerDischarge() {
        var alert = LowBatteryAlert()
        let fired = [40, 20, 15, 14, 13, 16, 14, 25, 30, 12].map { alert.update($0) }
        // Below 15 once; wobbling and 30 % do not re-arm; above 30 does.
        #expect(fired == [false, false, false, true, false, false, false, false, false, false])
        #expect(alert.update(31) == false)
        #expect(alert.update(10) == true)
    }

    @Test func orangeBelowFifteen() {
        #expect(LowBatteryAlert.isLow(14))
        #expect(!LowBatteryAlert.isLow(15))
    }
}

@MainActor
struct DeviceStoreFirmwareTests {
    @Test func lowBatteryNotifiesOnceEvenAcrossRelaunches() {
        let prefs = freshPreferences()
        var levels: [Int] = []
        let devices = DeviceStore(makeDriver: { FakeDriver() }, preferences: prefs)
        devices.onLowBattery = { levels.append($0) }
        devices.handle(.battery(14))
        devices.handle(.battery(12))
        let relaunched = DeviceStore(makeDriver: { FakeDriver() }, preferences: prefs)
        relaunched.onLowBattery = { levels.append($0) }
        relaunched.handle(.battery(11))
        #expect(levels == [14])
        relaunched.handle(.battery(80))
        relaunched.handle(.battery(9))
        #expect(levels == [14, 9])
    }

    @Test func aFirmwareUpdateHoldsOffReconnectsUntilItEnds() {
        let driver = FakeDriver()
        let prefs = freshPreferences()
        let id = UUID()
        prefs.set(PairedDevice(id: id.uuidString, name: "Omi").encoded, for: .btDevice)
        let devices = DeviceStore(makeDriver: { driver }, preferences: prefs, retryDelay: .milliseconds(1))
        var disconnects = 0
        devices.onDisconnect = { disconnects += 1 }
        devices.start()
        devices.handle(.connected(id: id, name: "Omi"))
        devices.handle(.info(model: "Omi CV 1", firmware: "3.0.21", manufacturer: nil, hardware: "1"))
        #expect(devices.liveFirmware == "3.0.21")
        #expect(devices.paired?.hardwareRevision == "1")

        devices.suspendForFirmwareUpdate()
        #expect(devices.connection == .disconnected)
        #expect(devices.liveFirmware == nil)
        devices.handle(.disconnected(id: id, error: nil))
        devices.handle(.bluetooth(.ready))
        devices.start()
        #expect(driver.connected == [id])
        #expect(disconnects >= 1)

        devices.resumeAfterFirmwareUpdate()
        #expect(driver.connected == [id, id])
        // The firmware read before the update is not taken for the running one.
        devices.handle(.connected(id: id, name: "Omi"))
        #expect(devices.liveFirmware == nil)
        #expect(devices.paired?.firmwareRevision == "3.0.21")
    }
}
