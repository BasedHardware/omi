import OmiTheme
import SwiftUI

/// Proactive notification card shown below the closed chrome inside the notch
/// body. The entire card opens the chat; dismiss (X) and Execute keep their
/// own hit regions in an overlay.
struct NotchNotificationCard: View {
  let notification: FloatingBarNotification

  var body: some View {
    if notification.assistantId == "reach_error" {
      reachErrorCard
    } else {
      notificationCard
    }
  }

  private var notificationCard: some View {
    Button {
      FloatingControlBarManager.shared.openNotificationAsChat(notification)
    } label: {
      HStack(alignment: .top, spacing: 10) {
        ZStack {
          RoundedRectangle(cornerRadius: 10)
            .fill(Color.white.opacity(0.08))
            .frame(width: 34, height: 34)

          Image(systemName: "bell.badge.fill")
            .font(.system(size: 14, weight: .semibold))
            .foregroundColor(.white)
        }

        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text(notification.title)
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(.white)
            .lineLimit(1)

          Text(notification.message)
            .scaledFont(size: 12)
            .foregroundColor(.white.opacity(0.72))
            .lineLimit(3)
            .fixedSize(horizontal: false, vertical: true)
        }

        Spacer(minLength: 0)

        // Reserve space so text never runs under the overlaid action buttons.
        Color.clear
          .frame(width: notification.assistantId == "task" ? 90 : 36, height: 18)
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.md)
      .frame(maxWidth: .infinity, alignment: .leading)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .overlay(alignment: .topTrailing) {
      HStack(spacing: OmiSpacing.xs) {
        // Execute is only meaningful for actionable (task) notifications.
        if notification.assistantId == "task" {
          Button {
            let model =
              ShortcutSettings.shared.selectedModel.isEmpty
              ? ModelQoS.Claude.defaultSelection
              : ShortcutSettings.shared.selectedModel
            let query = ProactiveTaskExecute.buildQuery(
              title: notification.title,
              message: notification.message
            )
            _ = AgentPillsManager.shared.spawn(
              query: query,
              model: model,
              originSurface: .floatingBar,
              systemPromptSuffix: ProactiveTaskExecute.systemPromptSuffix
            )
            FloatingControlBarManager.shared.dismissCurrentNotification()
          } label: {
            HStack(spacing: OmiSpacing.xxs) {
              Image(systemName: "sparkles")
                .font(.system(size: 9, weight: .bold))
              Text("Execute")
                .scaledFont(size: OmiType.micro, weight: .semibold)
            }
            .foregroundColor(.white)
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.xxs)
            .background(Color.white.opacity(0.18))
            .clipShape(Capsule())
          }
          .buttonStyle(.plain)
          .help("Spawn an agent to handle this")
        }

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
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.md)
    }
  }

  /// Hard reach failure (retries exhausted). Persists until the user picks
  /// Retry (re-runs the query, restarting backoff) or Skip (back to idle).
  private var reachErrorCard: some View {
    HStack(alignment: .center, spacing: OmiSpacing.sm) {
      Image(systemName: "exclamationmark.triangle.fill")
        .font(.system(size: 14, weight: .semibold))
        .foregroundColor(.white.opacity(0.9))

      VStack(alignment: .leading, spacing: 1) {
        Text(notification.title)
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(.white)
          .lineLimit(1)
        if !notification.message.isEmpty {
          Text(notification.message)
            .scaledFont(size: 11)
            .foregroundColor(.white.opacity(0.7))
            .lineLimit(1)
        }
      }

      Spacer(minLength: OmiSpacing.sm)

      Button {
        FloatingControlBarManager.shared.retryReachError()
      } label: {
        Text("Retry")
          .scaledFont(size: 12, weight: .semibold)
          .foregroundColor(.white)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xxs)
          .background(Color.white.opacity(0.18))
          .clipShape(Capsule())
      }
      .buttonStyle(.plain)

      Button {
        FloatingControlBarManager.shared.dismissReachError()
      } label: {
        Text("Skip")
          .scaledFont(size: 12, weight: .semibold)
          .foregroundColor(.white.opacity(0.6))
          .padding(.horizontal, OmiSpacing.xs)
          .padding(.vertical, OmiSpacing.xxs)
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.md)
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}
