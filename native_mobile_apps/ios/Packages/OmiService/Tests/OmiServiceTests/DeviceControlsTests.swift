import Foundation
import OmiDevice
import OmiPersistence
@testable import OmiService
import Testing

/// Records what the store writes to the Omi.
final class ControlDriver: DeviceDriving, @unchecked Sendable {
    let stream: (AsyncStream<OmiDeviceManager.Event>, AsyncStream<OmiDeviceManager.Event>.Continuation) = AsyncStream.makeStream()
    var events: AsyncStream<OmiDeviceManager.Event> {
        stream.0
    }

    private let lock = NSLock()
    private var _writes: [(OmiGATT.Control, Data)] = []
    var writes: [(OmiGATT.Control, Data)] {
        lock.withLock { _writes }
    }

    func startScan() {}
    func stopScan() {}
    func connect(_: UUID) {}
    func disconnect() {}
    func readBattery() {}
    func write(_ control: OmiGATT.Control, _ payload: Data) {
        lock.withLock { _writes.append((control, payload)) }
    }
}

@MainActor
struct ButtonRoutingTests {
    @Test func routesEveryFirmwareEvent() {
        func route(_ event: OmiGATT.ButtonEvent, _ action: DoubleTapAction = .endConversation, enabled: Bool = true) -> ButtonAction? {
            ButtonAction.route(event, doubleTap: action, actionsEnabled: enabled)
        }
        #expect(route(.doubleTap) == .endConversation)
        #expect(route(.doubleTap, .star) == .toggleStar)
        #expect(route(.doubleTap, .toggleMute) == .toggleMute)
        #expect(route(.singleTap) == .askToggle)
        #expect(route(.longPress) == .askHoldStart)
        #expect(route(.release) == .askHoldEnd)
        #expect(route(.press) == nil)
        #expect(route(.doubleTap, enabled: false) == nil)
        #expect(route(.singleTap, enabled: false) == nil)
    }

    /// Raw values are the Flutter `doubleTapAction` preference.
    @Test func doubleTapChoiceUsesFlutterPreference() {
        let prefs = freshPreferences()
        prefs.set(2, for: .doubleTapAction)
        let devices = DeviceStore(makeDriver: { ControlDriver() }, preferences: prefs)
        #expect(devices.doubleTapAction == .star)
        devices.doubleTapAction = .toggleMute
        #expect(prefs.integer(.doubleTapAction, default: 0) == 1)
        #expect(devices.buttonActionsEnabled)
    }

    @Test func doubleTapSetToStarDoesNotEndTheConversation() {
        let prefs = freshPreferences()
        let devices = DeviceStore(makeDriver: { ControlDriver() }, preferences: prefs)
        devices.doubleTapAction = .star
        var ended = 0
        var actions: [ButtonAction] = []
        devices.onDoubleTap = { ended += 1 }
        devices.onButtonAction = { actions.append($0) }
        devices.handle(.button(Data([2, 0, 0, 0, 0, 0, 0, 0])))
        devices.handle(.button(Data([1, 0, 0, 0, 0, 0, 0, 0])))
        #expect(ended == 0)
        #expect(actions == [.toggleStar, .askToggle])
        devices.buttonActionsEnabled = false
        devices.handle(.button(Data([2, 0, 0, 0])))
        #expect(actions.count == 2)
        #expect(!prefs.bool(.omiButtonActionsEnabled, default: true))
    }
}

@MainActor
struct DeviceControlsTests {
    let deviceID = UUID()

    func connected(_ driver: ControlDriver, gap: Duration = .milliseconds(1)) -> DeviceStore {
        let prefs = freshPreferences()
        prefs.set(PairedDevice(id: deviceID.uuidString, name: "Omi").encoded, for: .btDevice)
        let devices = DeviceStore(makeDriver: { driver }, preferences: prefs, findPulseGap: gap)
        devices.start()
        devices.handle(.connected(id: deviceID, name: "Omi"))
        return devices
    }

    @Test func controlsAppearOnlyForSupportedFirmware() {
        let driver = ControlDriver()
        let devices = connected(driver)
        #expect(!devices.canDimLED)
        devices.setLEDBrightness(50)
        #expect(driver.writes.isEmpty)
        devices.handle(.features(OmiGATT.Features(Data([0x80, 0x00, 0x00, 0x00]))))
        devices.handle(.ledBrightness(70))
        devices.handle(.micGain(4))
        #expect(devices.canDimLED)
        #expect(!devices.canSetMicGain)
        #expect(!devices.canFind)
        devices.setLEDBrightness(130)
        #expect(devices.ledBrightness == 100)
        #expect(driver.writes.map(\.1) == [Data([100])])
        #expect(driver.writes.first?.0 == .ledBrightness)
    }

    @Test func micGainWritesTheLevel() {
        let driver = ControlDriver()
        let devices = connected(driver)
        devices.handle(.features([.micGain, .haptic]))
        devices.handle(.micGain(3))
        devices.setMicGain(6)
        #expect(devices.micGain == 6)
        #expect(driver.writes.last?.0 == .micGain)
        #expect(driver.writes.last?.1 == Data([6]))
    }

    @Test func findMyOmiBuzzesThreeTimes() async {
        let driver = ControlDriver()
        let devices = connected(driver)
        devices.handle(.features(.haptic))
        await devices.findDevice()
        #expect(driver.writes.map(\.0) == [.haptic, .haptic, .haptic])
        #expect(driver.writes.map(\.1) == Array(repeating: Data([3]), count: 3))
        #expect(!devices.isFinding)
    }

    @Test func chargingSerialAndResetOnReconnect() {
        let driver = ControlDriver()
        let devices = connected(driver)
        devices.handle(.charging(true))
        devices.handle(.serialNumber("0A1B2C3D4E5F6789"))
        devices.handle(.features(.ledDimming))
        #expect(devices.isCharging == true)
        #expect(devices.paired?.serialNumber == "0A1B2C3D4E5F6789")
        devices.handle(.connected(id: deviceID, name: "Omi"))
        #expect(devices.isCharging == nil)
        #expect(devices.features == nil)
        #expect(devices.paired?.serialNumber == "0A1B2C3D4E5F6789")
    }
}
