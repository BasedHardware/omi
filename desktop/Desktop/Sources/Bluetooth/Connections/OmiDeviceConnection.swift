import Combine
import CoreBluetooth
import Foundation
import os.log

/// Device connection implementation for Omi and OpenGlass devices
/// Ported from: omi/app/lib/services/devices/omi_connection.dart
final class OmiDeviceConnection: BaseDeviceConnection {

    private let logger = Logger(subsystem: "me.omi.desktop", category: "OmiDeviceConnection")

    // MARK: - Initialization

    override init(device: BtDevice, transport: DeviceTransport) {
        super.init(device: device, transport: transport)
    }

    // MARK: - Connection

    override func connect() async throws {
        try await super.connect()

        // Check if this is an OpenGlass device (has image streaming)
        if await hasPhotoStreaming() && device.type == .omi {
            device.type = .openglass
            logger.info("Detected OpenGlass device (has image streaming)")
        }
    }

    // MARK: - Camera (OpenGlass)

    override func hasPhotoStreaming() async -> Bool {
        guard await isConnected() else { return false }

        do {
            // Try to read from image data stream to check if it exists
            _ = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.Omi.mainService,
                characteristicUUID: DeviceUUIDs.Omi.imageDataStream
            )
            return true
        } catch {
            return false
        }
    }

    override func startPhotoCapture() async {
        guard await isConnected() else { return }

        do {
            // 0x05 = capture photo every 5 seconds
            try await transport.writeCharacteristic(
                data: Data([0x05]),
                serviceUUID: DeviceUUIDs.Omi.mainService,
                characteristicUUID: DeviceUUIDs.Omi.imageCaptureControl,
                withResponse: true
            )
            logger.debug("Started photo capture")
        } catch {
            logger.error("Failed to start photo capture: \(error.localizedDescription)")
        }
    }

    override func stopPhotoCapture() async {
        guard await isConnected() else { return }

        do {
            // 0x00 = stop capture
            try await transport.writeCharacteristic(
                data: Data([0x00]),
                serviceUUID: DeviceUUIDs.Omi.mainService,
                characteristicUUID: DeviceUUIDs.Omi.imageCaptureControl,
                withResponse: true
            )
            logger.debug("Stopped photo capture")
        } catch {
            logger.error("Failed to stop photo capture: \(error.localizedDescription)")
        }
    }

    /// Take a single photo
    func takePhoto() async {
        guard await isConnected() else { return }

        do {
            // 0xFF (-1) = take single photo
            try await transport.writeCharacteristic(
                data: Data([0xFF]),
                serviceUUID: DeviceUUIDs.Omi.mainService,
                characteristicUUID: DeviceUUIDs.Omi.imageCaptureControl,
                withResponse: true
            )
            logger.debug("Taking single photo")
        } catch {
            logger.error("Failed to take photo: \(error.localizedDescription)")
        }
    }

    override func getImageStream() -> AsyncThrowingStream<OrientedImage, Error> {
        let rawStream = transport.getCharacteristicStream(
            serviceUUID: DeviceUUIDs.Omi.mainService,
            characteristicUUID: DeviceUUIDs.Omi.imageDataStream
        )

        return AsyncThrowingStream { continuation in
            Task { [weak self] in
                guard let self = self else {
                    continuation.finish()
                    return
                }

                var buffer = Data()
                var nextExpectedFrame = 0
                var isTransferring = false
                var currentOrientation: ImageOrientation = .orientation0

                // Check firmware version for orientation parsing
                let firmwareVersion = self.device.firmwareRevision ?? "1.0.0"
                let supportsOrientation = self.compareFirmwareVersion(firmwareVersion, isAtLeast: "2.1.1")

                do {
                    for try await chunk in rawStream {
                        guard chunk.count >= 2 else { continue }

                        let frameIndex = Int(chunk[0]) | (Int(chunk[1]) << 8)

                        // End of image marker 0xFFFF
                        if frameIndex == 0xFFFF {
                            if isTransferring && !buffer.isEmpty {
                                let image = OrientedImage(
                                    imageData: buffer,
                                    orientation: currentOrientation
                                )
                                continuation.yield(image)
                                self.logger.debug("Completed image: \(buffer.count) bytes")
                            }

                            // Reset for next image
                            buffer = Data()
                            isTransferring = false
                            nextExpectedFrame = 0
                            currentOrientation = .orientation0
                            continue
                        }

                        // Frame 0 = start of new image
                        if frameIndex == 0 {
                            buffer = Data()
                            isTransferring = true
                            nextExpectedFrame = 0
                            currentOrientation = .orientation0
                        }

                        // Ignore packets if not in transfer
                        guard isTransferring else { continue }

                        // Check frame sequence
                        if frameIndex == nextExpectedFrame {
                            if frameIndex == 0 {
                                if supportsOrientation && chunk.count > 2 {
                                    // New firmware: parse orientation
                                    currentOrientation = ImageOrientation.from(value: Int(chunk[2]))
                                    if chunk.count > 3 {
                                        buffer.append(chunk[3...])
                                    }
                                } else {
                                    // Old firmware: default to 180 degrees
                                    currentOrientation = .orientation180
                                    if chunk.count > 2 {
                                        buffer.append(chunk[2...])
                                    }
                                }
                            } else {
                                if chunk.count > 2 {
                                    buffer.append(chunk[2...])
                                }
                            }
                            nextExpectedFrame += 1
                        } else {
                            // Out of order - discard
                            self.logger.warning("Frame out of order: expected \(nextExpectedFrame), got \(frameIndex)")
                            buffer = Data()
                            isTransferring = false
                            nextExpectedFrame = 0
                        }

                        // Safety: prevent buffer overflow
                        if buffer.count > 200 * 1024 {
                            self.logger.warning("Buffer exceeded 200KB, resetting")
                            buffer = Data()
                            isTransferring = false
                            nextExpectedFrame = 0
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    private func compareFirmwareVersion(_ version: String, isAtLeast minVersion: String) -> Bool {
        let v1Parts = version.split(separator: ".").compactMap { Int($0) }
        let v2Parts = minVersion.split(separator: ".").compactMap { Int($0) }

        for i in 0..<max(v1Parts.count, v2Parts.count) {
            let v1 = i < v1Parts.count ? v1Parts[i] : 0
            let v2 = i < v2Parts.count ? v2Parts[i] : 0
            if v1 < v2 { return false }
            if v1 > v2 { return true }
        }
        return true
    }

    // MARK: - Settings

    override func setLedDimRatio(_ ratio: Int) async {
        guard await isConnected() else { return }

        do {
            let clampedRatio = max(0, min(100, ratio))
            try await transport.writeCharacteristic(
                data: Data([UInt8(clampedRatio)]),
                serviceUUID: DeviceUUIDs.Omi.settingsService,
                characteristicUUID: DeviceUUIDs.Omi.settingsDimRatio,
                withResponse: true
            )
        } catch {
            logger.error("Failed to set LED dim ratio: \(error.localizedDescription)")
        }
    }

    override func getLedDimRatio() async -> Int? {
        guard await isConnected() else { return nil }

        do {
            let data = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.Omi.settingsService,
                characteristicUUID: DeviceUUIDs.Omi.settingsDimRatio
            )
            return data.isEmpty ? nil : Int(data[0])
        } catch {
            logger.error("Failed to get LED dim ratio: \(error.localizedDescription)")
            return nil
        }
    }

    override func setMicGain(_ gain: Int) async {
        guard await isConnected() else { return }

        do {
            let clampedGain = max(0, min(100, gain))
            try await transport.writeCharacteristic(
                data: Data([UInt8(clampedGain)]),
                serviceUUID: DeviceUUIDs.Omi.settingsService,
                characteristicUUID: DeviceUUIDs.Omi.settingsMicGain,
                withResponse: true
            )
        } catch {
            logger.error("Failed to set mic gain: \(error.localizedDescription)")
        }
    }

    override func getMicGain() async -> Int? {
        guard await isConnected() else { return nil }

        do {
            let data = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.Omi.settingsService,
                characteristicUUID: DeviceUUIDs.Omi.settingsMicGain
            )
            return data.isEmpty ? nil : Int(data[0])
        } catch {
            logger.error("Failed to get mic gain: \(error.localizedDescription)")
            return nil
        }
    }

    // MARK: - WiFi Sync

    override func isWifiSyncSupported() async -> Bool {
        let features = await getFeatures()
        return features.contains(.wifi)
    }

    override func setupWifiSync(ssid: String, password: String) async -> WifiSyncSetupResult {
        guard await isConnected() else { return .connectionFailed() }

        // Validate credentials using the validator
        if let ssidError = WifiCredentialsValidator.validateSsid(ssid) {
            logger.error("Invalid SSID: \(ssidError)")
            return .failure(.ssidLengthInvalid, customMessage: ssidError)
        }

        if let passwordError = WifiCredentialsValidator.validatePassword(password) {
            logger.error("Invalid password: \(passwordError)")
            return .failure(.passwordLengthInvalid, customMessage: passwordError)
        }

        var command: [UInt8] = [0x01] // Setup command

        // SSID
        let ssidBytes = Array(ssid.utf8)
        command.append(UInt8(ssidBytes.count))
        command.append(contentsOf: ssidBytes)

        // Password
        let passwordBytes = Array(password.utf8)
        command.append(UInt8(passwordBytes.count))
        command.append(contentsOf: passwordBytes)

        do {
            // Start listening for response before sending command
            let responseStream = transport.getCharacteristicStream(
                serviceUUID: DeviceUUIDs.Storage.service,
                characteristicUUID: DeviceUUIDs.Storage.wifi
            )

            // Send the setup command
            try await transport.writeCharacteristic(
                data: Data(command),
                serviceUUID: DeviceUUIDs.Storage.service,
                characteristicUUID: DeviceUUIDs.Storage.wifi,
                withResponse: true
            )

            // Wait for response with timeout (5 seconds)
            let timeoutTask = Task {
                try await Task.sleep(nanoseconds: 5_000_000_000) // 5 seconds
                return WifiSyncSetupResult.timeout()
            }

            let responseTask = Task { () -> WifiSyncSetupResult in
                for try await data in responseStream {
                    if !data.isEmpty {
                        let responseCode = WifiSyncErrorCode.from(code: Int(data[0]))
                        if responseCode.isSuccess {
                            return .success()
                        } else {
                            return .failure(responseCode)
                        }
                    }
                }
                return .timeout()
            }

            // Race between timeout and response
            let result = await withTaskGroup(of: WifiSyncSetupResult.self) { group in
                group.addTask {
                    do {
                        return try await timeoutTask.value
                    } catch {
                        return .timeout()
                    }
                }

                group.addTask {
                    do {
                        return try await responseTask.value
                    } catch {
                        return .connectionFailed()
                    }
                }

                // Return the first completed result
                let firstResult = await group.next() ?? .timeout()

                // Cancel remaining tasks
                group.cancelAll()

                return firstResult
            }

            return result

        } catch {
            logger.error("Failed to setup WiFi sync: \(error.localizedDescription)")
            return .connectionFailed()
        }
    }

    override func startWifiSync() async -> Bool {
        guard await isConnected() else { return false }

        do {
            // 0x02 = WIFI_START command
            try await transport.writeCharacteristic(
                data: Data([0x02]),
                serviceUUID: DeviceUUIDs.Storage.service,
                characteristicUUID: DeviceUUIDs.Storage.wifi,
                withResponse: true
            )
            return true
        } catch {
            logger.error("Failed to start WiFi sync: \(error.localizedDescription)")
            return false
        }
    }

    override func stopWifiSync() async -> Bool {
        guard await isConnected() else { return false }

        do {
            // 0x03 = WIFI_SHUTDOWN command
            try await transport.writeCharacteristic(
                data: Data([0x03]),
                serviceUUID: DeviceUUIDs.Storage.service,
                characteristicUUID: DeviceUUIDs.Storage.wifi,
                withResponse: true
            )
            return true
        } catch {
            logger.error("Failed to stop WiFi sync: \(error.localizedDescription)")
            return false
        }
    }

    /// Get a stream of WiFi sync status updates
    override func getWifiSyncStatusStream() -> AsyncThrowingStream<Int, Error> {
        let stream = transport.getCharacteristicStream(
            serviceUUID: DeviceUUIDs.Storage.service,
            characteristicUUID: DeviceUUIDs.Storage.wifi
        )

        return AsyncThrowingStream { continuation in
            Task {
                do {
                    for try await data in stream {
                        if !data.isEmpty {
                            continuation.yield(Int(data[0]))
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }
}
