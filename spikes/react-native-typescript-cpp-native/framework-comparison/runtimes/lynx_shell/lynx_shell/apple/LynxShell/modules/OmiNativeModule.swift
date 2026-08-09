import Foundation

@objcMembers
public final class OmiNativeModule: NSObject, LynxModule {
  public static var name: String { "OmiNativeModule" }

  public static var methodLookup: [String: String] {
    [
      "getNativeCapabilities": NSStringFromSelector(#selector(getNativeCapabilities)),
      "normalizePacket": NSStringFromSelector(#selector(normalizePacket(_:)))
    ]
  }

  public init(param: Any) {
    super.init()
  }

  public override init() {
    super.init()
  }

  @objc public func getNativeCapabilities() -> NSString {
    let base = OmiNativeBoundaryBridge.capabilities()
    return "{\"framework\":\"lynx\",\"platform\":\"ios\",\"bridge\":\"lynx-native-module\",\"cppBoundary\":\"linked\",\"capabilities\":\(base)}" as NSString
  }

  @objc public func normalizePacket(_ raw: String) -> NSString {
    OmiNativeBoundaryBridge.normalizePacket(raw) as NSString
  }
}
