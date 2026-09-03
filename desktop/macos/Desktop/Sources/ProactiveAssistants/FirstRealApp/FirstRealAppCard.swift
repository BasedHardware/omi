import OmiTheme
import SwiftUI

/// The one-time "I can see <App>" card.
///
/// Persistent by contract — it is sent with `isPersistent: true` — so the bar's
/// six-second auto-dismiss never applies. Its exits are the user's (tap, ✕, or
/// starting push-to-talk) plus the coordinator's own 60-second timeout, and each
/// one is reported to `FirstRealAppCardCoordinator` so the funnel records
/// exactly one terminal phase.
///
/// It has its own card rather than reusing the generic notification view for one
/// reason: the generic ✕ goes straight to `dismissCurrentNotification`, which
/// leaves this feature unable to tell "the user closed it" from "it timed out"
/// — the two outcomes the activation experiment is measured on.
struct FirstRealAppCard: View {
  let notification: FloatingBarNotification
  let prompt: String

  var body: some View {
    Button {
      // Routed through the bar, not straight to the coordinator, so the card's
      // dismissal, queue advancement and standard click telemetry stay owned by
      // `FloatingControlBarManager`. It calls back into the coordinator through
      // the `askOmiPrefilled` action.
      FloatingControlBarManager.shared.openNotificationAsChat(notification)
    } label: {
      HStack(alignment: .top, spacing: OmiSpacing.md) {
        FloatingBarNotificationCardLead(
          copy: FloatingControlBarManager.notificationCardCopy(
            title: notification.title,
            message: notification.message,
            kind: notification.kind
          ),
          messageLineLimit: 2
        )
        Spacer(minLength: 0)

        // Reserve room so the copy never runs under the overlaid ✕.
        Color.clear
          .frame(width: 40, height: 20)
      }
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.md + 2)
      .frame(maxWidth: .infinity, alignment: .leading)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .overlay(alignment: .topTrailing) {
      Button {
        FirstRealAppCardCoordinator.shared.handleCardDismissed()
        FloatingControlBarManager.shared.dismissCurrentNotification()
      } label: {
        Image(systemName: "xmark")
          .font(.system(size: 10, weight: .bold))
          .foregroundColor(.white.opacity(0.62))
          .frame(width: 18, height: 18)
          .background(Color.white.opacity(0.08))
          .clipShape(Circle())
      }
      .buttonStyle(.plain)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.md)
      .accessibilityLabel("Dismiss")
    }
  }
}
