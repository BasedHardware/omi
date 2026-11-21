@preconcurrency import CoreBluetooth
import Foundation
@preconcurrency import iOSMcuManagerLibrary

/// Flashes a firmware package to the wearable (real: `McuFirmwareUpdater`; tests: a fake).
public protocol FirmwareUpdating: AnyObject, Sendable {
    /// Uploads `package` (an MCUboot OTA zip or a signed .bin on disk) to `deviceID` and has the
    /// bootloader install it. Yields upload progress from 0 to 1 and finishes once the device took
    /// the image and resets into it; throws when it did not. The caller frees the device first:
    /// this opens its own Bluetooth connection.
    @MainActor
    func update(deviceID: UUID, package: URL) -> AsyncThrowingStream<Double, any Error>
}

/// Omi firmware update over SMP (MCUmgr) with Nordic's iOSMcuManagerLibrary. The Omi CV1 runs
/// MCUboot in overwrite-only mode with two images (app core, network core) and
/// `CONFIG_NCS_SAMPLE_MCUMGR_BT_OTA_DFU` (`omi/firmware/omi/sysbuild.conf`, `omi.conf`).
/// Settings match the Flutter app (`firmware_mixin.dart` `startMCUDfu`).
public final class McuFirmwareUpdater: FirmwareUpdating, @unchecked Sendable {
    /// The running update; held so its delegate (weak in the library) stays alive.
    @MainActor private var session: Session?

    public init() {}

    @MainActor
    public func update(deviceID: UUID, package: URL) -> AsyncThrowingStream<Double, any Error> {
        let (stream, continuation) = AsyncThrowingStream.makeStream(of: Double.self)
        let images: [ImageManager.Image]
        do {
            images = try McuMgrPackage(from: package).images
        } catch {
            continuation.finish(throwing: error)
            return stream
        }
        let session = Session(deviceID: deviceID, images: images, continuation: continuation) { [weak self] in
            self?.session = nil
        }
        self.session = session
        continuation.onTermination = { reason in
            guard case .cancelled = reason else { return }
            Task { @MainActor in session.cancel() }
        }
        session.start()
        return stream
    }

    /// One update: a transport of its own (own CBCentralManager) on the same peripheral.
    /// The library calls every delegate method on the main queue.
    private final class Session: FirmwareUpgradeDelegate, @unchecked Sendable {
        private let transport: McuMgrBleTransport
        private let images: [ImageManager.Image]
        private let continuation: AsyncThrowingStream<Double, any Error>.Continuation
        private let ended: @MainActor () -> Void
        private var manager: FirmwareUpgradeManager?
        /// Overall progress across images: the library reports bytes per image.
        private var finishedBytes = 0
        private var lastSent = 0
        private var lastSize = 0
        private var total: Int

        init(
            deviceID: UUID,
            images: [ImageManager.Image],
            continuation: AsyncThrowingStream<Double, any Error>.Continuation,
            ended: @escaping @MainActor () -> Void
        ) {
            transport = McuMgrBleTransport(deviceID)
            self.images = images
            self.continuation = continuation
            self.ended = ended
            total = max(1, images.reduce(0) { $0 + $1.data.count })
        }

        @MainActor
        func start() {
            let manager = FirmwareUpgradeManager(transport: transport, delegate: self)
            self.manager = manager
            let configuration = FirmwareUpgradeConfiguration(
                estimatedSwapTime: 0,
                eraseAppSettings: true,
                pipelineDepth: 1,
                upgradeMode: .confirmOnly
            )
            manager.start(images: images, using: configuration)
        }

        @MainActor
        func cancel() {
            manager?.cancel()
            transport.close()
        }

        func upgradeDidStart(controller _: any FirmwareUpgradeController) {}

        func upgradeStateDidChange(from _: FirmwareUpgradeState, to _: FirmwareUpgradeState) {}

        func upgradeDidComplete() {
            continuation.yield(1)
            finish(nil)
        }

        func upgradeDidFail(inState _: FirmwareUpgradeState, with error: any Error) {
            finish(error)
        }

        func upgradeDidCancel(state _: FirmwareUpgradeState) {
            finish(CancellationError())
        }

        func uploadProgressDidChange(bytesSent: Int, imageSize: Int, timestamp _: Date) {
            // A smaller count than before means the next image started.
            if bytesSent < lastSent { finishedBytes += lastSize }
            lastSent = bytesSent
            lastSize = imageSize
            continuation.yield(min(1, Double(finishedBytes + bytesSent) / Double(total)))
        }

        private func finish(_ error: (any Error)?) {
            transport.close()
            continuation.finish(throwing: error)
            let ended = ended
            Task { @MainActor in ended() }
        }
    }
}
