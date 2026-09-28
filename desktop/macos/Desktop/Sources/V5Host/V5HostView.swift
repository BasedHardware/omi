import AppKit
import SwiftUI

#if canImport(OmiV5Runtime)
  import V5HostKit

  struct V5HostView: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
      V5HostKit.makeRootView()
    }

    func updateNSView(_ nsView: NSView, context: Context) {}
  }
#endif
