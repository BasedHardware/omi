import AppKit
import OmiTheme
import SwiftUI

/// Omi-owned window chrome that keeps the native macOS traffic lights while
/// replacing the opaque system title strip with a flush, draggable glass bar.
struct OmiWindowChromeBar: View {
  let pageTitle: String

  var body: some View {
    ZStack {
      OmiAdaptiveMaterialBackground(
        material: .hudWindow,
        blendingMode: .behindWindow,
        fallback: OmiColors.backgroundPrimary,
        materialOverlay: OmiColors.backgroundPrimary.opacity(0.40)
      )

      MainWindowDragRegion()

      HStack(spacing: OmiSpacing.sm) {
        Text("omi.")
          .scaledFont(size: OmiType.subheading, weight: .bold)
          .foregroundStyle(OmiColors.textPrimary)
          .tracking(-0.5)

        Rectangle()
          .fill(OmiColors.border.opacity(0.55))
          .frame(width: 1, height: 14)

        Text(pageTitle)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundStyle(OmiColors.textTertiary)

        Spacer(minLength: 0)
      }
      .padding(.leading, 82)
      .padding(.trailing, OmiSpacing.lg)
      .allowsHitTesting(false)
    }
    .frame(height: 44)
    .overlay(alignment: .bottom) {
      Rectangle()
        .fill(OmiColors.border.opacity(0.42))
        .frame(height: 1)
    }
    .accessibilityElement(children: .combine)
    .accessibilityLabel("Omi, \(pageTitle)")
  }
}

private struct MainWindowDragRegion: NSViewRepresentable {
  func makeNSView(context: Context) -> NSView {
    DragView()
  }

  func updateNSView(_ nsView: NSView, context: Context) {}

  private final class DragView: NSView {
    override func mouseDown(with event: NSEvent) {
      if event.clickCount == 2 {
        window?.zoom(nil)
      } else {
        window?.performDrag(with: event)
      }
    }
  }
}
