import OmiTheme
import SwiftUI

extension FloatingControlBarView {
  /// A proposed task surfaced while listening (I1): a suggestion the user must
  /// accept, not a save receipt. The wire text is the encoded
  /// `SuggestedTaskChatCard`; the pill shows the human description and offers
  /// Review (there is no Undo — nothing was written). Auto-collapses.
  @ViewBuilder
  func notchReceiptCard(_ notification: FloatingBarNotification) -> some View {
    let card = SuggestedTaskChatCard.parse(notification.title)
    HStack(spacing: 10) {
      Image(systemName: "checklist")
        .scaledFont(size: 12.5)
        .foregroundColor(NotchGlass.primary)
      VStack(alignment: .leading, spacing: 1) {
        Text("Suggested task")
          .scaledFont(size: 10)
          .foregroundColor(NotchGlass.ink(.w55))
        Text(card?.description ?? notification.title)
          .scaledFont(size: 12.5)
          .foregroundColor(NotchGlass.primary)
          .lineLimit(2)
      }
      Spacer(minLength: 8)
      Button {
        NotchMomentsCoordinator.shared.reviewLastReceipt()
        FloatingControlBarManager.shared.dismissCurrentNotification()
      } label: {
        Text("Review")
          .scaledFont(size: 11.5)
          .foregroundColor(NotchGlass.primary)
          .underline()
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}
