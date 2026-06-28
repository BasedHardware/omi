import AppKit
import SwiftUI

@MainActor
final class CloudConnectorGuidanceOverlay {
  static let shared = CloudConnectorGuidanceOverlay()

  private var window: NSWindow?
  private var dismissTask: Task<Void, Never>?

  private init() {}

  func presentClaudeConnectHint(windowFrame: CGRect, targetPoint: CGPoint) {
    dismissTask?.cancel()
    window?.close()

    let overlaySize = CGSize(width: 330, height: 118)
    let proposedOrigin = CGPoint(
      x: targetPoint.x - overlaySize.width / 2,
      y: targetPoint.y + 34
    )
    let frame = Self.clampedFrame(
      CGRect(origin: proposedOrigin, size: overlaySize),
      near: windowFrame
    )

    let view = CloudConnectorGuidanceView()
    let hostingController = NSHostingController(rootView: view)
    hostingController.view.frame = CGRect(origin: .zero, size: overlaySize)

    let panel = NSPanel(
      contentRect: frame,
      styleMask: [.borderless, .nonactivatingPanel],
      backing: .buffered,
      defer: false
    )
    panel.contentViewController = hostingController
    panel.isOpaque = false
    panel.backgroundColor = .clear
    panel.hasShadow = false
    panel.level = .popUpMenu
    panel.ignoresMouseEvents = true
    panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
    panel.animationBehavior = .none
    panel.orderFrontRegardless()
    window = panel

    dismissTask = Task { [weak self] in
      try? await Task.sleep(nanoseconds: 14_000_000_000)
      await MainActor.run {
        guard !Task.isCancelled else { return }
        self?.dismiss()
      }
    }
  }

  func dismiss() {
    dismissTask?.cancel()
    dismissTask = nil
    window?.close()
    window = nil
  }

  private static func clampedFrame(_ frame: CGRect, near windowFrame: CGRect) -> CGRect {
    let screen = NSScreen.screens.first { $0.frame.intersects(windowFrame) } ?? NSScreen.main
    guard let visibleFrame = screen?.visibleFrame else { return frame }
    return CGRect(
      x: min(max(frame.minX, visibleFrame.minX + 12), visibleFrame.maxX - frame.width - 12),
      y: min(max(frame.minY, visibleFrame.minY + 12), visibleFrame.maxY - frame.height - 12),
      width: frame.width,
      height: frame.height
    )
  }
}

private struct CloudConnectorGuidanceView: View {
  var body: some View {
    VStack(spacing: 8) {
      HStack(spacing: 10) {
        ZStack {
          Circle()
            .fill(OmiColors.success.opacity(0.18))
          Image(systemName: "arrow.down")
            .scaledFont(size: 15, weight: .bold)
            .foregroundColor(OmiColors.success)
        }
        .frame(width: 34, height: 34)

        VStack(alignment: .leading, spacing: 2) {
          Text("Finish in Claude")
            .scaledFont(size: 13, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text("Click the Connect button below.")
            .scaledFont(size: 12, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
        }
        Spacer(minLength: 0)
      }
      .padding(.horizontal, 14)
      .padding(.vertical, 12)
      .background(
        RoundedRectangle(cornerRadius: 18, style: .continuous)
          .fill(Color.black.opacity(0.88))
      )
      .overlay(
        RoundedRectangle(cornerRadius: 18, style: .continuous)
          .stroke(OmiColors.success.opacity(0.55), lineWidth: 1)
      )
      .shadow(color: .black.opacity(0.32), radius: 18, y: 8)

      TrianglePointer()
        .fill(OmiColors.success)
        .frame(width: 18, height: 13)
    }
    .padding(8)
  }
}

private struct TrianglePointer: Shape {
  func path(in rect: CGRect) -> Path {
    var path = Path()
    path.move(to: CGPoint(x: rect.midX, y: rect.maxY))
    path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
    path.addLine(to: CGPoint(x: rect.minX, y: rect.minY))
    path.closeSubpath()
    return path
  }
}
