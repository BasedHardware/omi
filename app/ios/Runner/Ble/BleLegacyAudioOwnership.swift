import Foundation

/// Native fail-closed policy for the legacy CV1 audio notification.
///
/// CoreBluetooth may restore a CCCD subscription before Dart rebuilds its
/// foreground transport. A storage-authoritative session deliberately omits
/// `nativeBleStreamConfig`, so a restored legacy notification must not consume
/// BLE bandwidth or cross the Flutter bridge while the ring protocol owns GATT.
struct BleLegacyAudioOwner: Equatable {
  let peripheralUuid: String
  let serviceUuid: String
  let characteristicUuid: String
}

enum BleLegacyAudioOwnershipDecision: Equatable {
  case notLegacyAudio
  case configuredOwner
  case orphanedLegacyAudio
}

enum BleLegacyAudioOwnershipPolicy {
  static let serviceUuid = "19b10000-e8f2-537e-4f6c-d104768a1214"
  static let characteristicUuid = "19b10001-e8f2-537e-4f6c-d104768a1214"

  static func owner(from rawConfig: String?) -> BleLegacyAudioOwner? {
    guard let rawConfig, !rawConfig.isEmpty,
      let data = rawConfig.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let deviceId = json["deviceId"] as? String, !deviceId.isEmpty,
      let serviceUuid = json["serviceUuid"] as? String, !serviceUuid.isEmpty,
      let characteristicUuid = json["characteristicUuid"] as? String,
      !characteristicUuid.isEmpty
    else {
      return nil
    }

    return BleLegacyAudioOwner(
      peripheralUuid: deviceId.lowercased(),
      serviceUuid: serviceUuid.lowercased(),
      characteristicUuid: characteristicUuid.lowercased()
    )
  }

  static func decision(
    peripheralUuid: String,
    serviceUuid: String,
    characteristicUuid: String,
    configuredOwner: BleLegacyAudioOwner?
  ) -> BleLegacyAudioOwnershipDecision {
    let service = serviceUuid.lowercased()
    let characteristic = characteristicUuid.lowercased()
    guard service == Self.serviceUuid, characteristic == Self.characteristicUuid else {
      return .notLegacyAudio
    }

    guard
      configuredOwner
        == BleLegacyAudioOwner(
          peripheralUuid: peripheralUuid.lowercased(),
          serviceUuid: service,
          characteristicUuid: characteristic
        )
    else {
      return .orphanedLegacyAudio
    }
    return .configuredOwner
  }
}
