import Foundation

@objcMembers
public final class OmiNativeModule: NSObject, LynxModule {
  public static var name: String { "OmiNativeModule" }

  public static var methodLookup: [String: String] {
    [
      "getNativeCapabilities": NSStringFromSelector(#selector(getNativeCapabilities)),
      "normalizePacket": NSStringFromSelector(#selector(normalizePacket(_:))),
      "getBluetoothState": NSStringFromSelector(#selector(getBluetoothState)),
      "startOmiScan": NSStringFromSelector(#selector(startOmiScan)),
      "stopOmiScan": NSStringFromSelector(#selector(stopOmiScan)),
      "getOmiScanResults": NSStringFromSelector(#selector(getOmiScanResults)),
      "connectOmi": NSStringFromSelector(#selector(connectOmi(_:))),
      "disconnectOmi": NSStringFromSelector(#selector(disconnectOmi))
    ]
  }

  private let bluetooth = OmiBluetoothController()

  public init(param: Any) { super.init() }
  public override init() { super.init() }

  @objc public func getNativeCapabilities() -> NSString {
    let base = OmiNativeBoundaryBridge.capabilities()
    return "{\"framework\":\"lynx\",\"platform\":\"ios\",\"bridge\":\"lynx-native-module\",\"cppBoundary\":\"linked\",\"capabilities\":\(base)}" as NSString
  }

  @objc public func normalizePacket(_ raw: String) -> NSString {
    OmiNativeBoundaryBridge.normalizePacket(raw) as NSString
  }

  @objc public func getBluetoothState() -> NSString { json(bluetooth.capabilities()) }
  @objc public func startOmiScan() -> NSString { json(bluetooth.startScan()) }
  @objc public func stopOmiScan() -> NSString { json(bluetooth.stopScan()) }
  @objc public func getOmiScanResults() -> NSString { json(bluetooth.scanResults()) }
  @objc public func connectOmi(_ identifier: String) -> NSString { json(bluetooth.connect(identifier: identifier)) }
  @objc public func disconnectOmi() -> NSString { json(bluetooth.disconnect()) }

  private func json(_ value: Any) -> NSString {
    guard JSONSerialization.isValidJSONObject(value),
          let data = try? JSONSerialization.data(withJSONObject: value),
          let text = String(data: data, encoding: .utf8) else { return "{}" }
    return text as NSString
  }
}
