import Foundation

private enum TestFailure: Error {
  case failed(String)
}

private func expectEqual<T: Equatable>(_ actual: T, _ expected: T, _ message: String) throws {
  guard actual == expected else {
    throw TestFailure.failed("\(message): expected \(expected), got \(actual)")
  }
}

@main
private struct BleLegacyAudioOwnershipTests {
  static func main() throws {
    let device = "47D3572B-2464-40C0-BBBE-3BFCD9EF1BE5"
    let service = BleLegacyAudioOwnershipPolicy.serviceUuid
    let characteristic = BleLegacyAudioOwnershipPolicy.characteristicUuid

    try expectEqual(
      BleLegacyAudioOwnershipPolicy.decision(
        peripheralUuid: device,
        serviceUuid: service,
        characteristicUuid: characteristic,
        configuredOwner: BleLegacyAudioOwnershipPolicy.owner(from: nil)
      ),
      .orphanedLegacyAudio,
      "omitted config must release a restored legacy audio notification"
    )

    try expectEqual(
      BleLegacyAudioOwnershipPolicy.owner(from: "{not-json"),
      nil,
      "malformed config must fail closed"
    )

    let matchingConfig = """
      {
        "deviceId":"\(device.lowercased())",
        "serviceUuid":"\(service.uppercased())",
        "characteristicUuid":"\(characteristic.uppercased())"
      }
      """
    try expectEqual(
      BleLegacyAudioOwnershipPolicy.decision(
        peripheralUuid: device,
        serviceUuid: service,
        characteristicUuid: characteristic,
        configuredOwner: BleLegacyAudioOwnershipPolicy.owner(from: matchingConfig)
      ),
      .configuredOwner,
      "matching configured legacy owner must retain its notification"
    )

    let otherDeviceConfig = matchingConfig.replacingOccurrences(
      of: device.lowercased(),
      with: "00000000-0000-0000-0000-000000000000"
    )
    try expectEqual(
      BleLegacyAudioOwnershipPolicy.decision(
        peripheralUuid: device,
        serviceUuid: service,
        characteristicUuid: characteristic,
        configuredOwner: BleLegacyAudioOwnershipPolicy.owner(from: otherDeviceConfig)
      ),
      .orphanedLegacyAudio,
      "a stale config for another pendant must not own this notification"
    )

    try expectEqual(
      BleLegacyAudioOwnershipPolicy.decision(
        peripheralUuid: device,
        serviceUuid: service,
        characteristicUuid: "19b10002-e8f2-537e-4f6c-d104768a1214",
        configuredOwner: nil
      ),
      .notLegacyAudio,
      "the guard must not interfere with storage or control characteristics"
    )

    print("BleLegacyAudioOwnershipTests: PASS")
  }
}
