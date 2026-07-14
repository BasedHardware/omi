import SwiftUI
import OmiTheme

// MARK: - ChatErrorCard
//
// Renders a single `ChatErrorState` as an inline, message-level card with
// a primary recovery CTA. Visual conventions follow the existing chat
// banners (tinted backdrop + SF Symbol + tinted border) so the surfaces
// feel like siblings.

struct ChatErrorCard: View {
  let state: ChatErrorState
  let onRecover: () -> Void
  let onDismiss: (() -> Void)?

  @State private var showDetails: Bool = false

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack(alignment: .top, spacing: OmiSpacing.sm) {
        Image(systemName: iconName)
          .scaledFont(size: OmiType.body)
          .foregroundColor(accentColor)
          .frame(width: 16, alignment: .center)

        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(headline)
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Text(detail)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
        }

        Spacer(minLength: 8)

        if let onDismiss = onDismiss {
          Button(action: onDismiss) {
            Image(systemName: "xmark")
              .scaledFont(size: OmiType.micro)
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
          .help("Dismiss")
        }
      }

      HStack(spacing: OmiSpacing.sm) {
        Button(action: onRecover) {
          Text(primaryCTATitle)
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(.white)
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.xxs)
            .background(accentColor.opacity(0.9))
            .clipShape(RoundedRectangle(cornerRadius: OmiChrome.badgeRadius))
        }
        .buttonStyle(.plain)

        if !detailsBody.isEmpty {
          Button(action: { showDetails.toggle() }) {
            HStack(spacing: OmiSpacing.hairline) {
              Text(showDetails ? "Hide details" : "Show details")
                .scaledFont(size: OmiType.caption)
              Image(systemName: showDetails ? "chevron.up" : "chevron.down")
                .scaledFont(size: OmiType.micro)
            }
            .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
        }

        Spacer()
      }

      if showDetails, !detailsBody.isEmpty {
        Text(detailsBody)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
          .fixedSize(horizontal: false, vertical: true)
          .padding(.top, OmiSpacing.hairline)
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .background(accentColor.opacity(0.08))
    .overlay(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .strokeBorder(accentColor.opacity(0.35), lineWidth: 1)
    )
    .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius))
  }

  // MARK: - State-specific copy

  private var iconName: String {
    switch state {
    case .authRequired:
      return "person.badge.key.fill"
    case .timeout:
      return "clock.badge.exclamationmark.fill"
    case .bridgeUnavailable:
      return "bolt.horizontal.circle.fill"
    case .interrupted:
      return "stop.circle.fill"
    case .noDataFound:
      return "magnifyingglass"
    }
  }

  private var accentColor: Color {
    switch state {
    case .authRequired:
      return .blue
    case .timeout, .interrupted:
      return .orange
    case .bridgeUnavailable:
      return .red
    case .noDataFound:
      return OmiColors.textTertiary
    }
  }

  private var headline: String {
    switch state {
    case .authRequired:
      return "Sign in to continue"
    case .timeout(let toolName):
      if let toolName = toolName {
        return "\(toolName) timed out"
      }
      return "AI took too long to respond"
    case .bridgeUnavailable(let reason):
      switch reason {
      case .nodeMissing:
        return "AI runtime missing"
      case .runtimeMissing:
        return "AI components missing"
      case .crashed:
        return "AI stopped unexpectedly"
      case .failedToStart:
        return "AI couldn't start"
      case .unknown:
        return "AI isn't running"
      }
    case .interrupted:
      return "Response stopped"
    case .noDataFound:
      return "I didn't find anything"
    }
  }

  private var detail: String {
    switch state {
    case .authRequired:
      return "Your session expired. Sign in again to keep chatting."
    case .timeout:
      return "Try again, or rephrase your question."
    case .bridgeUnavailable(let reason):
      switch reason {
      case .nodeMissing:
        return "Node.js wasn't found. Install the runtime to keep using AI chat."
      case .runtimeMissing:
        return "The AI components aren't installed. Install them to keep chatting."
      case .crashed:
        return "The AI stopped mid-turn. Try again to start a fresh response."
      case .failedToStart(let failure):
        switch failure {
        case .handshakeTimedOut:
          return "The AI took too long to start. Try again to start a fresh response."
        case .incompatibleHandshake:
          return "The AI needs to restart before it can respond. Try again."
        case .exitedDuringStartup, .launchFailed:
          return "The AI couldn't start. Try again to start a fresh response."
        }
      case .unknown:
        return "The AI is not responding. Try again to start a fresh response."
      }
    case .interrupted:
      return "Ask something new when you're ready."
    case .noDataFound:
      return "Try a different question, or be more specific."
    }
  }

  private var primaryCTATitle: String {
    switch state.primaryRecovery {
    case .retry:
      return "Retry"
    case .signIn:
      return "Sign in"
    case .installRuntime:
      return "Install runtime"
    case .dismiss:
      return "Try a different question"
    }
  }

  /// Optional disclosure body. Empty string = hide the disclosure button
  /// entirely. Kept generic — surfaces only a redacted, user-safe
  /// description of the failure class, never raw error text.
  private var detailsBody: String {
    switch state {
    case .timeout(let toolName):
      if let toolName = toolName {
        return "Tool: \(toolName)"
      }
      return ""
    case .bridgeUnavailable(let reason):
      switch reason {
      case .nodeMissing:
        return "Cause: node binary not found on PATH."
      case .runtimeMissing:
        return "Cause: bridge script missing on disk."
      case .crashed:
        return "Cause: bridge process exited."
      case .failedToStart(let failure):
        return "Cause: bridge start failed (\(failure.rawValue))."
      case .unknown:
        return ""
      }
    case .authRequired, .interrupted, .noDataFound:
      return ""
    }
  }
}
