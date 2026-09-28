import AppKit
import OmiV5Runtime

public enum V5HostKit {
  @MainActor
  public static func makeRootView() -> NSView {
    OmiV5Host.makeRootView(withInitialProperties: ["hostMode": true])
  }
}
