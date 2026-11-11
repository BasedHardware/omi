// The Swift Programming Language
// https://docs.swift.org/swift-book
import AVFoundation
import Foundation

public struct Device {
  public var id: String
}

public class OmiManager {
  public init() {}

  private static var singleton = OmiManager()
  private static var friend_singleton = FriendManager()
  var deviceCompletion: ((Device?, Error?) -> Void)?

  var seen_devices: [Friend] = []

  public static func startScan(completion: ((Device?, Error?) -> Void)?) {
    friend_singleton.deviceCompletion = { device, error in
      if let id = device?.id.uuidString {
        if singleton.seen_devices.firstIndex(where: { $0.id.uuidString == id }) == nil {
          singleton.seen_devices.append(device!)
        }
        completion?(Device(id: id), nil)
      } else {
        completion?(nil, error)
      }
    }
    friend_singleton.startScan()
  }

  public static func endScan() {
    self.friend_singleton.deviceCompletion = nil
    self.friend_singleton.bluetoothScanner.centralManager.stopScan()
  }

  public static func connectToDevice(device: Device) {
    if let device = self.singleton.seen_devices.first(where: { $0.id.uuidString == device.id }) {
      self.friend_singleton.connectToDevice(device: device)
    }
  }

  public static func connectionUpdated(completion: @escaping (Bool) -> Void) {
    self.friend_singleton.connectionStatus(completion: completion)
  }

  /// Default live transcription uses on-device Whisper (existing path).
  public static func getLiveTranscription(device: Device, completion: @escaping (String?) -> Void) {
    if let device = self.singleton.seen_devices.first(where: { $0.id.uuidString == device.id }) {
      self.friend_singleton.getLiveTranscription(device: device, completion: completion)
    }
  }

  public static func getLiveAudio(device: Device, completion: @escaping (URL?) -> Void) {
    if let device = self.singleton.seen_devices.first(where: { $0.id.uuidString == device.id }) {
      self.friend_singleton.getRawAudio(device: device, completion: completion)
    }
  }

  /// Streaming STT factory for Deepgram / Parakeet.
  /// Whisper device path remains `getLiveTranscription`.
  public static func makeTranscriber(
    engine: OmiSttEngine,
    deepgramAPIKey: String? = nil,
    parakeetAPIURL: String? = ProcessInfo.processInfo.environment["HOSTED_PARAKEET_API_URL"],
    onTranscript: @escaping OmiTranscriptHandler
  ) throws -> OmiStreamingTranscriber {
    try OmiSttFactory.makeStreaming(
      engine: engine,
      deepgramAPIKey: deepgramAPIKey,
      parakeetAPIURL: parakeetAPIURL,
      onTranscript: onTranscript
    )
  }
}
