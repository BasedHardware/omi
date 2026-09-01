import OmiTheme
import SwiftUI

/// Assistant ids the first-run engine and the scenario onboarding use for their notch cards.
/// The bar picks a body by these; the engines never render anything themselves.
enum FirstRunNotchCardIdentity {
  /// The persistent guidance chip ("Open something you're working on").
  static let guide = "first_run_guide"
  /// Cards the first run delivers (focus, the returned reminder, the loop acknowledgement).
  static let card = "first_run_card"
  /// Cards the canned onboarding scenario fires (the order-confirmation reminder).
  static let scenario = "onboarding_scenario"

  static func isGuide(_ notification: FloatingBarNotification) -> Bool {
    notification.assistantId == guide
  }

  static func isFirstRunCard(_ notification: FloatingBarNotification) -> Bool {
    notification.assistantId == card || notification.assistantId == scenario
  }
}

/// A button the card renders, resolved from the notification's action by the bar view.
struct FirstRunCardButton: Identifiable, Equatable {
  enum Emphasis: Equatable { case primary, secondary }
  let id: String
  let title: String
  let emphasis: Emphasis
  /// The seam payload sent when tapped.
  let action: String
  let actionID: String

  /// The buttons a card action carries, in display order, with the seam strings
  /// `FloatingBarCardActionDispatcher` expects for each.
  nonisolated static func buttons(for descriptor: FloatingBarNotificationAction.ScenarioDescriptor)
    -> [FirstRunCardButton]
  {
    let id = descriptor.id
    switch descriptor.kind {
    case "onboarding_remind_me":
      return [
        FirstRunCardButton(
          id: "remind", title: "Remind me", emphasis: .primary, action: "onboarding_remind_me", actionID: id),
        FirstRunCardButton(
          id: "not-now", title: "Not now", emphasis: .secondary, action: "onboarding_not_now", actionID: id),
      ]
    case "first_run_focus_return":
      return [
        FirstRunCardButton(
          id: "back", title: "Back to it", emphasis: .primary, action: "first_run_focus_return", actionID: id),
        FirstRunCardButton(
          id: "snooze", title: "5 more minutes", emphasis: .secondary, action: "first_run_focus_snooze", actionID: id),
      ]
    case "context_reminder":
      return [
        FirstRunCardButton(
          id: "done", title: "Done", emphasis: .primary, action: "context_reminder_done", actionID: id),
        FirstRunCardButton(
          id: "tomorrow", title: "Remind me tomorrow", emphasis: .secondary, action: "context_reminder_snooze",
          actionID: id),
      ]
    case "first_run_open_summary":
      return [
        FirstRunCardButton(
          id: "open", title: "Open", emphasis: .primary, action: "first_run_open_summary", actionID: id)
      ]
    default:
      return []
    }
  }

  nonisolated static func symbol(for descriptor: FloatingBarNotificationAction.ScenarioDescriptor) -> String {
    switch descriptor.kind {
    case "onboarding_remind_me": return "bell.badge"
    case "first_run_focus_return": return "scope"
    case "context_reminder": return "arrow.uturn.backward"
    case "first_run_open_summary": return "text.document"
    default: return "sparkles"
    }
  }
}

/// The guidance chip: one line of instruction that stays until the step it names is observed.
///
/// Deliberately quieter than a proactive card: no icon tile, one eyebrow, the instruction as the
/// title, and the hint as a second line. It reads as Omi speaking, not as an alert.
struct FirstRunGuideChipView: View {
  let notification: FloatingBarNotification

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      VStack(alignment: .leading, spacing: 3) {
        HStack(spacing: OmiSpacing.xxs) {
          Circle()
            .fill(Color.white.opacity(0.85))
            .frame(width: 5, height: 5)
          Text("OMI · NEXT STEP")
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundColor(.white.opacity(0.5))
            .tracking(0.8)
        }
        Text(notification.title)
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(.white)
          .lineLimit(2)
          .multilineTextAlignment(.leading)
          .fixedSize(horizontal: false, vertical: true)
        if !notification.message.isEmpty {
          Text(notification.message)
            .scaledFont(size: OmiType.body)
            .foregroundColor(.white.opacity(0.62))
            .lineLimit(2)
            .multilineTextAlignment(.leading)
            .fixedSize(horizontal: false, vertical: true)
        }
      }
      Spacer(minLength: OmiSpacing.xs)
      Color.clear.frame(width: 28, height: 20)
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.md)
    .frame(maxWidth: .infinity, alignment: .leading)
    .overlay(alignment: .topTrailing) {
      // A user dismissal of the guide reaches the first-run engine through the manager's
      // `.firstRunNotificationDismissed` post; nothing else is needed here.
      FirstRunDismissButton {
        FloatingControlBarManager.shared.dismissCurrentNotification(kind: .user)
      }
    }
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("first-run-guide-chip")
  }
}

/// A first-run or scenario card with explicit buttons.
///
/// Same chrome as the other proactive cards (icon tile, eyebrow, message) so the user learns one
/// shape, plus a button row. Tapping the body opens the card in chat like every other card; the
/// buttons are the explicit decisions the card exists for.
struct FirstRunActionCardView: View {
  let notification: FloatingBarNotification
  let buttons: [FirstRunCardButton]
  let symbol: String

  @State private var didAct = false

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Button {
        FloatingControlBarManager.shared.openNotificationAsChat(notification)
      } label: {
        HStack(alignment: .top, spacing: OmiSpacing.md) {
          ZStack {
            RoundedRectangle(cornerRadius: 13, style: .continuous)
              .fill(
                LinearGradient(
                  colors: [Color.white.opacity(0.18), Color.white.opacity(0.08)],
                  startPoint: .top, endPoint: .bottom)
              )
              .overlay(
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                  .strokeBorder(Color.white.opacity(0.12), lineWidth: 1)
              )
              .frame(width: 44, height: 44)
            Image(systemName: symbol)
              .font(.system(size: 17, weight: .semibold))
              .foregroundColor(.white)
          }

          VStack(alignment: .leading, spacing: 3) {
            Text(notification.title)
              .scaledFont(size: OmiType.caption, weight: .semibold)
              .foregroundColor(.white.opacity(0.5))
              .lineLimit(1)
            Text(notification.message)
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundColor(.white)
              .lineLimit(3)
              .multilineTextAlignment(.leading)
              .fixedSize(horizontal: false, vertical: true)
          }
          Spacer(minLength: OmiSpacing.xs)
          Color.clear.frame(width: 28, height: 20)
        }
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)

      if !buttons.isEmpty {
        HStack(spacing: OmiSpacing.xs) {
          ForEach(buttons) { button in
            Button {
              guard !didAct else { return }
              didAct = true
              FloatingBarCardActionDispatcher.dispatch(action: button.action, id: button.actionID) {
                FloatingControlBarManager.shared.dismissCurrentNotification(kind: .user)
              }
            } label: {
              Text(button.title)
                .scaledFont(size: OmiType.caption, weight: .semibold)
                .foregroundColor(button.emphasis == .primary ? Color.black.opacity(0.85) : .white)
                .padding(.horizontal, OmiSpacing.md)
                .padding(.vertical, OmiSpacing.xs)
                .background(
                  Capsule().fill(button.emphasis == .primary ? Color.white : Color.white.opacity(0.14)))
            }
            .buttonStyle(.plain)
            .disabled(didAct)
            .accessibilityIdentifier("first-run-card-\(button.id)")
          }
          if InterjectFeature.isEnabled {
            Spacer(minLength: OmiSpacing.xs)
            Text(InterjectReplyHint.text(tokens: ShortcutSettings.shared.pttShortcut.displayTokens))
              .scaledFont(size: OmiType.micro, weight: .medium)
              .foregroundColor(.white.opacity(0.45))
              .lineLimit(1)
          }
        }
        .padding(.leading, 44 + OmiSpacing.md)
      }
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.md + 2)
    .frame(maxWidth: .infinity, alignment: .leading)
    .overlay(alignment: .topTrailing) {
      FirstRunDismissButton {
        FloatingControlBarManager.shared.dismissCurrentNotification()
      }
    }
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("first-run-card")
  }
}

/// The same dismiss circle every other card uses, factored so the two views above stay in step.
struct FirstRunDismissButton: View {
  let action: () -> Void

  var body: some View {
    Button(action: action) {
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
