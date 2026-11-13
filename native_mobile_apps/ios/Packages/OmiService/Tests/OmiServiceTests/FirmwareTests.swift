import Foundation
import OmiCore
import OmiDevice
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
final class FakeFirmwareHost: FirmwareDeviceHost {
    var paired: PairedDevice?
    var connection: DeviceStore.Connection = .connected
    var battery: Int? = 80
    var liveFirmware: String?
    private(set) var log: [String] = []

    init(firmware: String = "3.0.21") {
        var device = PairedDevice(id: UUID().uuidString, name: "Omi")
        device.modelNumber = "Omi CV 1"
        device.firmwareRevision = firmware
        paired = device
        liveFirmware = firmware
    }

    func suspendForFirmwareUpdate() {
        log.append("suspend")
        connection = .disconnected
        liveFirmware = nil
    }

    func resumeAfterFirmwareUpdate() {
        log.append("resume")
    }
}

/// Plays a scripted upload: progress values, then success or a failure.
final class FakeUpdater: FirmwareUpdating, @unchecked Sendable {
    var progress: [Double] = [0.25, 0.5, 1]
    var failure: (any Error)?
    /// Keep the upload open; the test drives `running` itself.
    var holds = false
    private(set) var running: AsyncThrowingStream<Double, any Error>.Continuation?
    private(set) var flashed: [URL] = []

    @MainActor
    func update(deviceID _: UUID, package: URL) -> AsyncThrowingStream<Double, any Error> {
        flashed.append(package)
        let (stream, continuation) = AsyncThrowingStream.makeStream(of: Double.self)
        if holds {
            running = continuation
            return stream
        }
        for value in progress {
            continuation.yield(value)
        }
        continuation.finish(throwing: failure)
        return stream
    }
}

@MainActor
struct FirmwareStoreTests {
    let api = FakeAPIClient()
    let host = FakeFirmwareHost()
    let updater = FakeUpdater()
    let prefs = freshPreferences()

    func store(now: @escaping () -> Date = { Fixtures.now }, download: (@Sendable (URL) async throws -> URL)? = nil) -> FirmwareStore {
        api.latestFirmwareRelease = Fixtures.firmwareRelease
        let file = FileManager.default.temporaryDirectory.appending(path: "omi-test-\(UUID().uuidString).zip")
        return FirmwareStore(
            api: api, devices: host, updater: updater, preferences: prefs,
            download: download ?? { _ in file }, now: now, handOverDelay: .zero
        )
    }

    @Test func offersANewerReleaseAndChecksAtMostOnceADay() async {
        var clock = Fixtures.now
        let firmware = store(now: { clock })
        await firmware.checkIfDue()
        #expect(firmware.available?.version == "3.0.22")
        await firmware.checkIfDue()
        clock += 23 * 60 * 60
        await firmware.checkIfDue()
        #expect(api.firmwareChecks == ["Omi CV 1@3.0.21"])
        clock += 2 * 60 * 60
        await firmware.checkIfDue()
        #expect(api.firmwareChecks.count == 2)
    }

    @Test func theDailyCheckSurvivesARelaunch() async {
        await store().checkIfDue()
        let relaunched = store()
        await relaunched.checkIfDue()
        #expect(relaunched.available?.version == "3.0.22")
        #expect(api.firmwareChecks.count == 1)
    }

    @Test func upToDateOrUnknownVersionsOfferNothing() async {
        let current = FakeFirmwareHost(firmware: "3.0.22")
        let firmware = FirmwareStore(api: api, devices: current, updater: updater, preferences: prefs)
        api.latestFirmwareRelease = Fixtures.firmwareRelease
        await firmware.checkIfDue()
        #expect(firmware.available == nil)
        current.liveFirmware = nil
        let unknown = FirmwareStore(api: api, devices: current, updater: updater, preferences: freshPreferences())
        await unknown.checkIfDue()
        #expect(api.firmwareChecks == ["Omi CV 1@3.0.22"])
    }

    @Test func aFailedCheckIsNotRetriedOnEveryRead() async {
        let firmware = store()
        api.fail(with: .transport("offline"))
        await firmware.checkIfDue()
        api.fail(with: nil)
        await firmware.checkIfDue()
        #expect(firmware.available == nil)
        #expect(api.firmwareChecks.isEmpty)
    }

    @Test func updatesThenWaitsForTheOmiToComeBackOnTheNewVersion() async {
        let firmware = store()
        await firmware.checkIfDue()
        await firmware.install()
        #expect(firmware.phase == .restarting)
        #expect(host.log == ["suspend", "resume"])
        #expect(updater.flashed.count == 1)
        // Reconnected: the old revision is not read yet, then the new one arrives.
        firmware.deviceInfoChanged()
        #expect(firmware.phase == .restarting)
        host.liveFirmware = "3.0.22"
        firmware.deviceInfoChanged()
        #expect(firmware.phase == .finished(version: "3.0.22"))
        #expect(firmware.available == nil)
    }

    @Test func reportsUploadProgressWhileTheOmiIsHandedOver() async {
        let firmware = store()
        updater.holds = true
        await firmware.checkIfDue()
        let install = Task { await firmware.install() }
        while updater.running == nil {
            await Task.yield()
        }
        #expect(firmware.phase == .installing(0))
        #expect(firmware.isBusy)
        #expect(host.log == ["suspend"])
        updater.running?.yield(0.4)
        for _ in 0 ..< 100 where firmware.phase != .installing(0.4) {
            await Task.yield()
        }
        #expect(firmware.phase == .installing(0.4))
        // Nothing else may start, or the device be checked, mid-update.
        await firmware.install()
        await firmware.checkIfDue()
        #expect(updater.flashed.count == 1)
        updater.running?.finish()
        await install.value
        #expect(firmware.phase == .restarting)
    }

    @Test func theOmiComingBackOnTheOldVersionIsAFailure() async {
        let firmware = store()
        await firmware.checkIfDue()
        await firmware.install()
        host.liveFirmware = "3.0.21"
        firmware.deviceInfoChanged()
        #expect(firmware.phase == .failed(.install))
        #expect(firmware.available != nil)
    }

    @Test func refusesBelowTwentyPercentOrWithoutAConnection() async {
        let firmware = store()
        await firmware.checkIfDue()
        host.battery = 19
        await firmware.install()
        #expect(firmware.phase == .failed(.lowBattery))
        host.battery = nil
        await firmware.install()
        #expect(firmware.phase == .failed(.lowBattery))
        host.battery = 20
        host.connection = .disconnected
        await firmware.install()
        #expect(firmware.phase == .failed(.notConnected))
        #expect(host.log.isEmpty)
        #expect(updater.flashed.isEmpty)
    }

    @Test func aFailedDownloadLeavesTheOmiAlone() async {
        let firmware = store(download: { _ in throw APIError.transport("offline") })
        await firmware.checkIfDue()
        await firmware.install()
        #expect(firmware.phase == .failed(.download))
        #expect(host.log.isEmpty)
    }

    @Test func aFailedUploadHandsTheOmiBack() async {
        let firmware = store()
        updater.failure = CancellationError()
        await firmware.checkIfDue()
        await firmware.install()
        #expect(firmware.phase == .failed(.install))
        #expect(host.log == ["suspend", "resume"])
        firmware.dismissResult()
        #expect(firmware.phase == .idle)
        #expect(firmware.available?.version == "3.0.22")
    }

    @Test func nothingStartsWithoutAnOffer() async {
        let firmware = store()
        await firmware.install()
        #expect(firmware.phase == .idle)
        #expect(updater.flashed.isEmpty)
    }
}
