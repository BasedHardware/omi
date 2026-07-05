import Flutter

enum CameraFacing {
  case front
  case back
}

@MainActor
final class MetaMockDeviceManager {
  fileprivate var mockDevicesSink: FlutterEventSink?

  init() {}

  func setMockDevicesSink(_ sink: FlutterEventSink?) {
    mockDevicesSink = sink
    sink?([])
  }

  func enable(initiallyRegistered: Bool, initialPermissionsGranted: Bool) {}

  func disable() {}

  func isEnabled() -> Bool { false }

  func pairRayBanMeta() -> String { "" }

  func unpair(uuid: String) throws { throw MockError.unavailable }

  func pairedDevices() -> [[String: Any]] { [] }

  func powerOn(uuid: String) throws { throw MockError.unavailable }

  func powerOff(uuid: String) throws { throw MockError.unavailable }

  func don(uuid: String) throws { throw MockError.unavailable }

  func doff(uuid: String) throws { throw MockError.unavailable }

  func fold(uuid: String) throws { throw MockError.unavailable }

  func unfold(uuid: String) throws { throw MockError.unavailable }

  func setPermission(permission: String, status: String) throws {
    throw MockError.unavailable
  }

  func setPermissionRequestResult(permission: String, status: String) throws {
    throw MockError.unavailable
  }

  func setCameraFacing(uuid: String, facing: CameraFacing) async throws {
    throw MockError.unavailable
  }

  func setCameraFeed(uuid: String, filePath: String?) async throws {
    throw MockError.unavailable
  }

  func setCapturedImage(uuid: String, filePath: String?) async throws {
    throw MockError.unavailable
  }
}

enum MockError: LocalizedError {
  case unavailable

  var errorDescription: String? {
    switch self {
    case .unavailable:
      return "Mock Device Kit unavailable in Omi4Meta install build"
    }
  }
}
