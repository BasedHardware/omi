import Foundation

final class OmiBatchAudioWriter {
  static let shared = OmiBatchAudioWriter()

  func stop(_: String) {}

  func handle(
    peripheralUuid _: String,
    serviceUuid _: String,
    characteristicUuid _: String,
    value _: Data
  ) -> Bool {
    false
  }
}

final class LimitlessFlashDrainEngine {
  static let shared = LimitlessFlashDrainEngine()

  func onDeviceDisconnected(_: String) {}
  func onDeviceReady(_: String) {}

  func handle(
    peripheralUuid _: String,
    serviceUuid _: String,
    characteristicUuid _: String,
    value _: Data
  ) -> Bool {
    false
  }
}
