import Foundation

enum BleNotificationRoute: Equatable {
  case limitlessFlash
  case batchAudio
  case dart
}

/// Keeps unrelated BLE notifications off the native batch-capture hot paths.
///
/// Both native handlers consult UserDefaults (and may parse JSON) before they
/// can reject a packet. Ring-sync traffic is much hotter than audio, so routing
/// by the protocol's fixed service/characteristic identity first prevents that
/// policy work from running for every storage notification.
enum BleNotificationRouter {
  private static let omiServiceUuid = "19b10000-e8f2-537e-4f6c-d104768a1214"
  private static let omiAudioCharacteristicUuid = "19b10001-e8f2-537e-4f6c-d104768a1214"
  private static let friendPendantServiceUuid = "1a3fd0e7-b1f3-ac9e-2e49-b647b2c4f8da"
  private static let friendPendantAudioCharacteristicUuid = "01000000-1111-1111-1111-111111111111"
  private static let limitlessServiceUuid = "632de001-604c-446b-a80f-7963e950f3fb"
  private static let limitlessReceiveCharacteristicUuid = "632de003-604c-446b-a80f-7963e950f3fb"

  static func route(serviceUuid: String, characteristicUuid: String) -> BleNotificationRoute {
    let service = serviceUuid.lowercased()
    let characteristic = characteristicUuid.lowercased()

    if service == limitlessServiceUuid, characteristic == limitlessReceiveCharacteristicUuid {
      return .limitlessFlash
    }
    if (service == omiServiceUuid && characteristic == omiAudioCharacteristicUuid)
      || (service == friendPendantServiceUuid
        && characteristic == friendPendantAudioCharacteristicUuid)
    {
      return .batchAudio
    }
    return .dart
  }
}
