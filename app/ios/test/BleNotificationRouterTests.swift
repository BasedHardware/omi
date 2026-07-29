import Foundation

private func expect(
  _ actual: BleNotificationRoute,
  _ expected: BleNotificationRoute,
  _ message: String,
  file: StaticString = #filePath,
  line: UInt = #line
) {
  guard actual == expected else {
    fatalError("\(file):\(line): \(message): expected \(expected), got \(actual)")
  }
}

private func testRoutesOnlyKnownNativeCaptureCharacteristics() {
  expect(
    BleNotificationRouter.route(
      serviceUuid: "632DE001-604C-446B-A80F-7963E950F3FB",
      characteristicUuid: "632DE003-604C-446B-A80F-7963E950F3FB"
    ),
    .limitlessFlash,
    "Limitless receive notifications must reach the native flash drain"
  )
  expect(
    BleNotificationRouter.route(
      serviceUuid: "19B10000-E8F2-537E-4F6C-D104768A1214",
      characteristicUuid: "19B10001-E8F2-537E-4F6C-D104768A1214"
    ),
    .batchAudio,
    "Omi audio notifications must reach native batch capture"
  )
  expect(
    BleNotificationRouter.route(
      serviceUuid: "1A3FD0E7-B1F3-AC9E-2E49-B647B2C4F8DA",
      characteristicUuid: "01000000-1111-1111-1111-111111111111"
    ),
    .batchAudio,
    "Friend pendant audio notifications must reach native batch capture"
  )
}

private func testStorageAndControlNotificationsBypassNativeCapturePolicy() {
  for characteristic in [
    "30295781-4301-eabd-2904-2849adfeae43",
    "30295782-4301-eabd-2904-2849adfeae43",
    "00002a19-0000-1000-8000-00805f9b34fb",
  ] {
    expect(
      BleNotificationRouter.route(
        serviceUuid: "30295780-4301-eabd-2904-2849adfeae43",
        characteristicUuid: characteristic
      ),
      .dart,
      "non-audio notification must bypass native capture policy"
    )
  }
}

private func testWrongCharacteristicWithinKnownServiceFallsThrough() {
  expect(
    BleNotificationRouter.route(
      serviceUuid: "632de001-604c-446b-a80f-7963e950f3fb",
      characteristicUuid: "632de002-604c-446b-a80f-7963e950f3fb"
    ),
    .dart,
    "Limitless TX characteristic is not a native receive hot path"
  )
  expect(
    BleNotificationRouter.route(
      serviceUuid: "19b10000-e8f2-537e-4f6c-d104768a1214",
      characteristicUuid: "19b10002-e8f2-537e-4f6c-d104768a1214"
    ),
    .dart,
    "Omi codec notifications must not consult batch capture policy"
  )
}

@main
private enum BleNotificationRouterTests {
  static func main() {
    testRoutesOnlyKnownNativeCaptureCharacteristics()
    testStorageAndControlNotificationsBypassNativeCapturePolicy()
    testWrongCharacteristicWithinKnownServiceFallsThrough()
    print("BleNotificationRouterTests: PASS")
  }
}
