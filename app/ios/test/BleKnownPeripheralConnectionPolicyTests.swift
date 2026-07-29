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
private struct BleKnownPeripheralConnectionPolicyTests {
  static func main() throws {
    try expectEqual(
      BleKnownPeripheralConnectionPolicy.action(isConnected: true),
      .rediscoverServices,
      "an OS-restored physical link must republish GATT readiness"
    )
    try expectEqual(
      BleKnownPeripheralConnectionPolicy.action(isConnected: false),
      .connect,
      "a disconnected known peripheral must start a physical connection"
    )

    print("BleKnownPeripheralConnectionPolicyTests: PASS")
  }
}
