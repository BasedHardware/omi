import OmiTheme
import SwiftUI

/// Modal overlay shown when the user hits a free-tier usage cap
/// (transcription minutes, monthly chat/floating-bar messages, etc).
///
/// Rendered as a `.overlay` on `DesktopHomeView.mainContent` so it appears
/// above every page. The user can dismiss it with the X button or by clicking the
/// dim outside the card; clicking "Upgrade" navigates to Settings → Plan & Usage.
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
      // The modal dim. `Ink.primary` rather than a literal black: it is `labelColor`, so it darkens
      // this light-pinned page and would lighten a dark one — one value, and it can never invert.
      Ink.primary.opacity(0.24)
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
              // `secondary` and not the glance rung: this card is glass, which carries two rungs.
              .foregroundColor(Ink.secondary)
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
              .fill(Ink.rowFill)
              .frame(width: 64, height: 64)
            Image(systemName: "exclamationmark.triangle.fill")
              .scaledFont(size: OmiType.title, weight: .semibold)
              .foregroundColor(Ink.primary)
          }

          VStack(spacing: OmiSpacing.sm) {
            Text(headline)
              .inkStyle(.stepHeadline, color: Ink.primary)
              .multilineTextAlignment(.center)

            Text(body_text)
              .inkStyle(.prose, color: Ink.secondary)
              .multilineTextAlignment(.center)
              .fixedSize(horizontal: false, vertical: true)
              .padding(.horizontal, OmiSpacing.lg)
          }

          VStack(spacing: OmiSpacing.sm) {
            // Stadium, not a rounded rectangle, and the label ladder inverted rather than an accent
            // fill — `InkButton` is the one action shape in this system.
            InkButton("Upgrade", action: onUpgrade)
              .frame(maxWidth: .infinity)

            InkButton("Bring your own keys", kind: .secondary, action: onBringYourOwnKeys)
              .frame(maxWidth: .infinity)
          }
          .padding(.horizontal, OmiSpacing.xxl)
        }
        .padding(.bottom, OmiSpacing.xxl)
      }
      .frame(width: 380)
      // The card paints no ground of its own; the glass owns it, and brings the corner, the edge and
      // the one ambient shadow with it.
      .inkGlassPanel()
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
