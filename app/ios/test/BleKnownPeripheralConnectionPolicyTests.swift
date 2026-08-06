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
    try expectEqual(
      BleRestoredPeripheralPolicy.action(backgroundModeEnabled: false),
      .releaseConnection,
      "an unapproved background restore must release the one-connection pendant"
    )
    try expectEqual(
      BleRestoredPeripheralPolicy.action(backgroundModeEnabled: true),
      .restoreConnection,
      "Background Mode opt-in must preserve CoreBluetooth restoration"
    )
    try expectEqual(
      BleRestoredPeripheralPolicy.shouldDeferConnect(
        requiresForegroundActivation: true
      ),
      true,
      "Flutter cannot reclaim a released pendant before the foreground callback"
    )
    try expectEqual(
      BleRestoredPeripheralPolicy.shouldDeferConnect(
        requiresForegroundActivation: false
      ),
      false,
      "the foreground callback or Background Mode opt-in clears the gate"
    )
    try expectEqual(
      BleRestoredPeripheralPolicy.shouldResumeDeferredConnect(
        requiresForegroundActivation: true,
        applicationIsActive: false
      ),
      false,
      "an inactive restoration launch must not consume foreground authority"
    )
    try expectEqual(
      BleRestoredPeripheralPolicy.shouldResumeDeferredConnect(
        requiresForegroundActivation: true,
        applicationIsActive: true
      ),
      true,
      "Bluetooth becoming ready in an active app may resume deferred ownership"
    )

    print("BleKnownPeripheralConnectionPolicyTests: PASS")
  }
}
