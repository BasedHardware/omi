import SwiftUI
import OmiTheme

/// Modal overlay shown when the user hits a free-tier usage cap
/// (transcription minutes, monthly chat/floating-bar messages, etc).
///
/// Rendered as a `.overlay` on `DesktopHomeView.mainContent` so it appears
/// above every page. The user can dismiss it with the X button or the
/// "Not now" button; clicking "Upgrade" navigates to Settings → Plan & Usage.
struct UsageLimitPopupView: View {
  let reason: String
  let onUpgrade: () -> Void
  let onDismiss: () -> Void
  let onBringYourOwnKeys: () -> Void

  private var headline: String {
    "You've hit your monthly limit"
  }

  private var body_text: String {
    switch reason {
    case "transcription":
      return "You've hit your monthly limit. Upgrade to make sure your new recordings aren't lost."
    case "chat", "floating_bar":
      return "You've hit your monthly limit. Upgrade to keep chatting with Omi without restrictions."
    default:
      // Covers "trial_expired" (menu-bar toggles in OmiApp.swift) and any
      // future caller. The previous default copy talked about recordings,
      // which was misleading for grandfathered Neo users whose listening
      // was never actually at risk — they were tripping a stale
      // isPaywalled flag (now self-healed by #7517) while at their chat
      // cap, and the recording-loss wording read as a data-loss threat.
      return "You've hit your monthly limit. Upgrade to keep using Omi without restrictions."
    }
  }

  var body: some View {
    ZStack {
      // Semi-transparent backdrop, tap-to-dismiss
      Color.black.opacity(0.55)
        .ignoresSafeArea()
        .onTapGesture { onDismiss() }

      // Centered card
      VStack(spacing: 0) {
        // Close X in the top-right corner
        HStack {
          Spacer()
          Button(action: onDismiss) {
            Image(systemName: "xmark")
              .scaledFont(size: OmiType.body, weight: .semibold)
              .foregroundColor(OmiColors.textTertiary)
              .padding(OmiSpacing.sm)
              .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
        }
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.top, OmiSpacing.sm)

        VStack(spacing: OmiSpacing.xl) {
          // Icon
          ZStack {
            Circle()
              .fill(OmiColors.accent.opacity(0.15))
              .frame(width: 64, height: 64)
            Image(systemName: "exclamationmark.triangle.fill")
              .scaledFont(size: OmiType.title, weight: .semibold)
              .foregroundColor(OmiColors.accent)
          }

          VStack(spacing: OmiSpacing.sm) {
            Text(headline)
              .scaledFont(size: OmiType.heading, weight: .bold)
              .foregroundColor(OmiColors.textPrimary)
              .multilineTextAlignment(.center)

            Text(body_text)
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)
              .multilineTextAlignment(.center)
              .fixedSize(horizontal: false, vertical: true)
              .padding(.horizontal, OmiSpacing.lg)
          }

          VStack(spacing: OmiSpacing.sm) {
            Button(action: onUpgrade) {
              Text("Upgrade")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.backgroundPrimary)
                .frame(maxWidth: .infinity)
                .frame(height: 44)
                .background(
                  RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                    .fill(OmiColors.accent)
                )
            }
            .buttonStyle(.plain)

            Button(action: onBringYourOwnKeys) {
              Text("Bring your own keys")
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(OmiColors.accent)
                .frame(maxWidth: .infinity)
                .frame(height: 32)
            }
            .buttonStyle(.plain)
          }
          .padding(.horizontal, OmiSpacing.xxl)
        }
        .padding(.bottom, OmiSpacing.xxl)
      }
      .frame(width: 380)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
          .fill(OmiColors.backgroundRaised)
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
              .stroke(OmiColors.border, lineWidth: 1)
          )
      )
      .shadow(color: .black.opacity(0.5), radius: 24, y: 8)
    }
    .transition(.opacity.animation(OmiMotion.gated(.easeInOut(duration: 0.2))))
  }
}

#if canImport(PreviewsMacros)
#Preview {
  UsageLimitPopupView(
    reason: "transcription",
    onUpgrade: {},
    onDismiss: {},
    onBringYourOwnKeys: {}
  )
  .frame(width: 900, height: 600)
}
#endif
