import OmiTheme
import SwiftUI

extension FloatingControlBarView {
  /// Durable receipt — "✓ Saved to Tasks — <task>" with Review and Undo, shown
  /// only after Omi can read the task through the canonical action-items path.
  /// Monochrome, on the pill's black glass. Auto-collapses.
  @ViewBuilder
  func notchReceiptCard(_ notification: FloatingBarNotification) -> some View {
    HStack(spacing: 10) {
      Text(notification.title)
        .scaledFont(size: 12.5)
        .foregroundColor(.white)
        .lineLimit(1)
      Spacer(minLength: 8)
      Button {
        NotchMomentsCoordinator.shared.reviewLastReceipt()
        FloatingControlBarManager.shared.dismissCurrentNotification()
      } label: {
        Text("Review")
          .scaledFont(size: 11.5)
          .foregroundColor(.white)
          .underline()
      }
      .buttonStyle(.plain)
      Button {
        NotchMomentsCoordinator.shared.undoLastReceipt()
        FloatingControlBarManager.shared.dismissCurrentNotification()
      } label: {
        Text("Undo")
          .scaledFont(size: 11.5)
          .foregroundColor(.white.opacity(0.55))
          .underline()
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}
