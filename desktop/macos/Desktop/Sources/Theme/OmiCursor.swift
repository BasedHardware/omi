import AppKit
import SwiftUI

private final class OmiCursorRectView: NSView {
  var cursor: NSCursor

  init(cursor: NSCursor) {
    self.cursor = cursor
    super.init(frame: .zero)
  }

  @available(*, unavailable)
  required init?(coder: NSCoder) {
    fatalError("init(coder:) has not been implemented")
  }

  override func resetCursorRects() {
    super.resetCursorRects()
    addCursorRect(bounds, cursor: cursor)
  }

  override func hitTest(_ point: NSPoint) -> NSView? {
    nil
  }
}

private struct OmiCursorRectRepresentable: NSViewRepresentable {
  let cursor: NSCursor

  func makeNSView(context: Context) -> OmiCursorRectView {
    OmiCursorRectView(cursor: cursor)
  }

  func updateNSView(_ nsView: OmiCursorRectView, context: Context) {
    nsView.cursor = cursor
    nsView.window?.invalidateCursorRects(for: nsView)
  }
}

package extension View {
  /// Registers a window-owned pointing-hand cursor rect without balancing a
  /// fragile `NSCursor.push()` / `pop()` stack during fast pointer movement.
  func omiPointerCursor(isEnabled: Bool = true) -> some View {
    overlay {
      if isEnabled {
        OmiCursorRectRepresentable(cursor: .pointingHand)
          .allowsHitTesting(false)
      }
    }
  }

  /// Keeps custom text-entry surfaces using the native insertion cursor.
  func omiIBeamCursor(isEnabled: Bool = true) -> some View {
    overlay {
      if isEnabled {
        OmiCursorRectRepresentable(cursor: .iBeam)
          .allowsHitTesting(false)
      }
    }
  }
}
