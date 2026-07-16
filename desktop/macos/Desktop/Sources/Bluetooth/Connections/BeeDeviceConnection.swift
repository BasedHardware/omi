@preconcurrency import CoreBluetooth
import Foundation
import os.log

/// Device connection implementation for Bee devices
/// Uses AAC audio codec with ADTS framing
/// Ported from: omi/app/lib/services/devices/bee_connection.dart
final class BeeDeviceConnection: BaseDeviceConnection {

  // MARK: - Constants

  private static let controlCharacteristicUUID = "05e1f93c-d8d0-5ed8-dd88-379e4c1a3e3e"
  private static let audioCharacteristicUUID = "b189a505-a86c-11ee-a5fb-8f2089a49e7e"

  private enum Command {
    static let mute: UInt16 = 0xC006
    static let unmute: UInt16 = 0xC006
    static let battery: UInt16 = 0xC00F
  }

  // MARK: - Private Properties

  private let logger = Logger(subsystem: "me.omi.desktop", category: "BeeDeviceConnection")

  private var audioBuffer = [UInt8]()
  private var controlSubscription: Task<Void, Never>?
  private var audioSubscription: Task<Void, Never>?
  private let responseOperations: DeviceOperationBroker<UInt16, Data>
  private let responseGate = UncorrelatedOperationGate<UInt16>()
  private let commandQueue = DeviceCommandQueue()
  private var audioStartAttempted = false
  private lazy var audioStreamController = DeviceAudioStreamController(
    start: { [weak self] in
      guard let self else { throw DeviceTransportError.disposed }
      try await self.startAudioSession()
    },
    stop: { [weak self] in
      guard let self else { return }
      try await self.stopAudioSession()
    }
  )

  // MARK: - Initialization

  override init(
    device: BtDevice,
    transport: DeviceTransport,
    operationClock: any DeviceOperationClock = ContinuousDeviceOperationClock()
  ) {
    self.responseOperations = DeviceOperationBroker(clock: operationClock)
    super.init(
      device: device,
      transport: transport,
      operationClock: operationClock
    )
  }

  // MARK: - Connection

  override func prepareDeviceAfterConnect() async throws {
    try await operationClock.sleep(for: .seconds(1))

    startControlListener()
    startAudioListener()
  }

  override func teardownDevice() async {
    await audioStreamController.finish()
    await commandQueue.close()
    audioBuffer.removeAll(keepingCapacity: false)

    controlSubscription?.cancel()
    audioSubscription?.cancel()
    controlSubscription = nil
    audioSubscription = nil
    await responseOperations.cancelAll(reason: .disconnected)
    responseGate.reset()
  }

  // MARK: - Listeners

  private func startControlListener() {
    let stream = transport.getCharacteristicStream(
      serviceUUID: DeviceUUIDs.Bee.service,
      characteristicUUID: CBUUID(string: Self.controlCharacteristicUUID)
    )

    controlSubscription = Task { [weak self] in
      do {
        for try await data in stream {
          self?.handleControlResponse(Array(data))
        }
      } catch {
        self?.logger.debug("Control stream ended")
      }
    }
  }

  private func startAudioListener() {
    let stream = transport.getCharacteristicStream(
      serviceUUID: DeviceUUIDs.Bee.service,
      characteristicUUID: CBUUID(string: Self.audioCharacteristicUUID)
    )

    audioSubscription = Task { [weak self] in
      do {
        for try await data in stream {
          if let frame = self?.processAudioPacket(Array(data)) {
            self?.audioStreamController.yield(Data(frame))
          }
        }
      } catch {
        self?.logger.debug("Audio stream ended")
      }
    }
  }

  // MARK: - Response Handling

  /// Parses one physical control notification. Internal for deterministic
  /// command-correlation tests without Bluetooth hardware.
  func handleControlResponse(_ data: [UInt8]) {
    guard data.count >= 2 else { return }

    let responseCode = UInt16(data[0]) | (UInt16(data[1]) << 8)
    let payload = data.count > 2 ? Array(data.dropFirst(2)) : []

    // Check for echo response (0x8000)
    if responseCode == 0x8000 && payload.count >= 2 {
      let echoedCmd = UInt16(payload[0]) | (UInt16(payload[1]) << 8)
      let actualPayload = payload.count > 2 ? Array(payload.dropFirst(2)) : []

      completeResponse(commandID: echoedCmd, payload: actualPayload)
    } else {
      completeResponse(commandID: responseCode, payload: payload)
    }
  }

  private func completeResponse(commandID: UInt16, payload: [UInt8]) {
    guard let handle = responseGate.takeHandleForCallback(key: commandID) else { return }
    Task {
      await responseOperations.succeed(
        handle: handle,
        value: Data(payload)
      )
    }
  }

  // MARK: - Audio Processing

  /// Process AAC audio packet with ADTS framing
  func processAudioPacket(_ data: [UInt8]) -> [UInt8]? {
    guard data.count >= 2 else { return nil }

    audioBuffer.append(contentsOf: data.dropFirst(2))
    return Self.nextADTSFrame(from: &audioBuffer)
  }

  /// Pop the next complete ADTS/AAC frame from `buffer`, skipping leading
  /// non-sync or malformed-header bytes. Returns nil when no complete valid
  /// frame is available yet.
  ///
  /// A valid ADTS frame is at least 7 bytes (the header length is part of the
  /// frameLength field). A decoded `frameLength < 7` — e.g. a false sync where
  /// 0xFF 0xFx matched inside AAC payload after a dropped BLE notification — was
  /// previously accepted: `buffer.count >= 0` is always true, `prefix(0)` is
  /// empty, and `removeFirst(0)` advances nothing, so the corrupt header stayed
  /// at the head and every later packet re-hit it — audio went permanently
  /// silent while the buffer grew without bound. Treat `< 7` as a false sync and
  /// advance one byte so the scanner keeps making progress.
  nonisolated static func nextADTSFrame(from buffer: inout [UInt8]) -> [UInt8]? {
    while buffer.count >= 7 {
      // Look for ADTS sync word (0xFF 0xFx)
      guard buffer[0] == 0xFF, (buffer[1] & 0xF0) == 0xF0 else {
        buffer.removeFirst()
        continue
      }

      // Extract frame length from ADTS header
      let frameLength = (Int(buffer[3] & 0x03) << 11) | (Int(buffer[4]) << 3) | (Int(buffer[5] & 0xE0) >> 5)

      guard frameLength >= 7 else {
        // False sync: 0xFF 0xFx matched but the header is invalid.
        buffer.removeFirst()
        continue
      }

      if buffer.count >= frameLength {
        let frame = Array(buffer.prefix(frameLength))
        buffer.removeFirst(frameLength)
        return frame
      }
      break
    }
    return nil
  }

  // MARK: - Command Sending

  private func sendCommand(cmdId: UInt16, payload: [UInt8]) async throws -> [UInt8]? {
    try await commandQueue.run { [weak self] in
      guard let self else { throw DeviceTransportError.disposed }
      return try await self.sendCommandSerially(cmdId: cmdId, payload: payload)
    }
  }

  private func sendCommandSerially(cmdId: UInt16, payload: [UInt8]) async throws -> [UInt8]? {
    guard responseGate.canStart(cmdId) else {
      throw DeviceConnectionError.operationFailed(
        "A previous command response is ambiguous; reconnect the device"
      )
    }
    let command: [UInt8] = [UInt8(cmdId & 0xFF), UInt8((cmdId >> 8) & 0xFF)] + payload

    do {
      let response = try await responseOperations.perform(
        key: cmdId,
        timeout: .seconds(5),
        onTerminal: { [weak self] handle, termination in
          self?.responseGate.terminal(handle: handle, termination: termination)
        }
      ) { [weak self] handle in
        guard let self else { throw DeviceTransportError.disposed }
        guard self.responseGate.register(handle) else {
          throw DeviceConnectionError.operationFailed(
            "Command callback identity is no longer trustworthy"
          )
        }
        try await self.transport.writeCharacteristic(
          data: Data(command),
          serviceUUID: DeviceUUIDs.Bee.service,
          characteristicUUID: CBUUID(string: Self.controlCharacteristicUUID),
          withResponse: true
        )
      }
      return Array(response)
    } catch DeviceOperationBrokerError.timedOut {
      return nil
    }
  }

  // MARK: - Battery

  override func getBatteryLevel() async -> Int {
    guard await isConnected() else { return -1 }

    do {
      guard let response = try await sendCommand(cmdId: Command.battery, payload: []),
        response.count >= 2
      else {
        return -1
      }
      return Int(response[0])
    } catch {
      logger.debug("Error retrieving battery: \(error.localizedDescription)")
      return -1
    }
  }

  /// Get battery state including charging status
  func getBatteryState() async -> (level: Int, isCharging: Bool)? {
    guard await isConnected() else { return nil }

    do {
      guard let response = try await sendCommand(cmdId: Command.battery, payload: []),
        response.count >= 2
      else {
        return nil
      }
      return (level: Int(response[0]), isCharging: response[1] != 0)
    } catch {
      return nil
    }
  }

  override func getBatteryLevelStream() -> AsyncThrowingStream<Int, Error> {
    // Bee uses command-based battery retrieval, poll every 60 seconds
    return AsyncThrowingStream { [weak self] continuation in
      let pollingTask = Task { [weak self] in
        guard let self = self else {
          continuation.finish()
          return
        }

        var lastLevel: Int?

        // Get initial battery level
        let initialLevel = await self.getBatteryLevel()
        if initialLevel >= 0 {
          lastLevel = initialLevel
          continuation.yield(initialLevel)
        }

        // Poll every 60 seconds
        while await self.isConnected() {
          do {
            try await self.operationClock.sleep(for: .seconds(60))
          } catch {
            break
          }
          guard !Task.isCancelled else { break }

          let level = await self.getBatteryLevel()
          if level >= 0 && level != lastLevel {
            lastLevel = level
            continuation.yield(level)
          }
        }

        continuation.finish()
      }
      continuation.onTermination = { @Sendable _ in
        pollingTask.cancel()
      }
    }
  }

  // MARK: - Audio

  override func getAudioCodec() async -> BleAudioCodec {
    .aac
  }

  override func getAudioStream() -> AsyncThrowingStream<Data, Error> {
    audioStreamController.makeStream()
  }

  private func startAudioSession() async throws {
    audioBuffer.removeAll(keepingCapacity: true)
    audioStartAttempted = true
    guard try await sendCommand(cmdId: Command.unmute, payload: [0x01]) != nil else {
      throw DeviceConnectionError.operationFailed("Bee did not acknowledge audio start")
    }
  }

  private func stopAudioSession() async throws {
    // Notifications can still arrive while the mute acknowledgement is in
    // flight. Clear both before and after teardown so no partial AAC frame
    // can cross the physical recording-session boundary.
    defer { audioBuffer.removeAll(keepingCapacity: true) }
    audioBuffer.removeAll(keepingCapacity: true)
    guard audioStartAttempted else { return }
    audioStartAttempted = false

    if responseGate.canStart(Command.mute) {
      do {
        guard try await sendCommand(cmdId: Command.mute, payload: [0x00]) != nil else {
          throw DeviceConnectionError.operationFailed(
            "Bee did not acknowledge audio stop"
          )
        }
        return
      } catch {
        await transport.disconnect()
        throw error
      }
    }

    // Unmute and mute share one uncorrelated device command ID. If setup
    // was cancelled after the unmute write, its response key is poisoned;
    // issue the compensating mute directly on the still-valid BLE write
    // channel, then retire the physical session rather than reopening that
    // command ID and risking a late mute response aliasing a new unmute.
    let command = [
      UInt8(Command.mute & 0xFF),
      UInt8((Command.mute >> 8) & 0xFF),
      0x00,
    ]
    do {
      try await commandQueue.run { [weak self] in
        guard let self else { throw DeviceTransportError.disposed }
        try await self.transport.writeCharacteristic(
          data: Data(command),
          serviceUUID: DeviceUUIDs.Bee.service,
          characteristicUUID: CBUUID(string: Self.controlCharacteristicUUID),
          withResponse: true
        )
      }
    } catch {
      logger.debug("Compensating Bee mute could not be confirmed: \(error.localizedDescription)")
    }
    await transport.disconnect()
    throw DeviceConnectionError.operationFailed(
      "Bee audio command identity is ambiguous; reconnect the device"
    )
  }

  // MARK: - Unsupported Features

  override func getButtonState() async -> [UInt8] { [] }
  override func getButtonStream() -> AsyncThrowingStream<[UInt8], Error> {
    AsyncThrowingStream { $0.finish() }
  }
  override func hasPhotoStreaming() async -> Bool { false }
  override func getAccelerometerStream() -> AsyncThrowingStream<AccelerometerData, Error> {
    AsyncThrowingStream { $0.finish() }
  }
  override func getFeatures() async -> OmiFeatures { [] }

  // MARK: - Device Info

  override func updateDeviceInfo() async {
    device.modelNumber = "Bee"
    device.firmwareRevision = "1.0.0"
    device.hardwareRevision = "1.0.0"
    device.manufacturerName = "Bee"
  }
}
