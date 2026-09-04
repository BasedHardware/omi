import OmiTheme
import SwiftUI

/// Notch card for a place-bound reminder: Done / Remind me tomorrow.
///
/// Same chrome as the other proactive cards (icon tile, eyebrow, message) so
/// the user learns one shape. The buttons are the explicit decisions the card
/// exists for; tapping the body opens it in chat like every other card.
struct ContextReminderCard: View {
  let notification: FloatingBarNotification
  let reminderID: String

  @State private var didAct = false

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Button {
        FloatingControlBarManager.shared.openNotificationAsChat(notification)
      } label: {
        HStack(alignment: .top, spacing: OmiSpacing.md) {
          FloatingBarNotificationCardLead(
            copy: ProactiveNotificationCopy.CardLines(
              caption: notification.title,
              heading: notification.message,
              detail: nil,
              systemImage: "arrow.uturn.backward"
            ),
            messageLineLimit: 3
          )
          Spacer(minLength: OmiSpacing.xs)
          Color.clear.frame(width: 28, height: 20)
        }
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)

      HStack(spacing: OmiSpacing.xs) {
        Button {
          guard !didAct else { return }
          didAct = true
          ContextReminderCoordinator.shared.markDone(reminderID: reminderID) { succeeded in
            if !succeeded { didAct = false }
          }
        } label: {
          Text("Done")
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundColor(Color.black.opacity(0.85))
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.xs)
            .background(Capsule().fill(Color.white))
        }
        .buttonStyle(.plain)
        .disabled(didAct)
        .accessibilityIdentifier("context-reminder-done")

        Button {
          guard !didAct else { return }
          didAct = true
          ContextReminderCoordinator.shared.snoozeUntilTomorrow(reminderID: reminderID) { succeeded in
            if !succeeded { didAct = false }
          }
        } label: {
          Text("Remind me tomorrow")
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundColor(.white)
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.xs)
            .background(Capsule().fill(Color.white.opacity(0.14)))
        }
        .buttonStyle(.plain)
        .disabled(didAct)
        .accessibilityIdentifier("context-reminder-snooze")
      }
      .padding(.leading, 44 + OmiSpacing.md)
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.md + 2)
    .frame(maxWidth: .infinity, alignment: .leading)
    .overlay(alignment: .topTrailing) {
      Button {
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
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("context-reminder-card")
    .onChange(of: reminderID) { _, _ in
      // A replacement reminder reuses this persistent card branch; its buttons
      // must start enabled rather than inheriting the previous card's didAct.
      didAct = false
    }
  }
}
