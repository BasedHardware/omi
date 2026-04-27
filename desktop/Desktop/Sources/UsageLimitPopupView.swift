import SwiftUI

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
      return "You've hit your monthly limit. Upgrade to make sure your new recordings aren't lost."
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
              .scaledFont(size: 14, weight: .semibold)
              .foregroundColor(OmiColors.textTertiary)
              .padding(8)
              .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
        }
        .padding(.horizontal, 8)
        .padding(.top, 8)

        VStack(spacing: 20) {
          // Icon
          ZStack {
            Circle()
              .fill(OmiColors.purplePrimary.opacity(0.15))
              .frame(width: 64, height: 64)
            Image(systemName: "exclamationmark.triangle.fill")
              .scaledFont(size: 28, weight: .semibold)
              .foregroundColor(OmiColors.purplePrimary)
          }

          VStack(spacing: 8) {
            Text(headline)
              .scaledFont(size: 20, weight: .bold)
              .foregroundColor(OmiColors.textPrimary)
              .multilineTextAlignment(.center)

            Text(body_text)
              .scaledFont(size: 14)
              .foregroundColor(OmiColors.textTertiary)
              .multilineTextAlignment(.center)
              .fixedSize(horizontal: false, vertical: true)
              .padding(.horizontal, 16)
          }

          VStack(spacing: 10) {
            Button(action: onUpgrade) {
              Text("Upgrade")
                .scaledFont(size: 15, weight: .semibold)
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .frame(height: 44)
                .background(
                  RoundedRectangle(cornerRadius: 10)
                    .fill(OmiColors.purplePrimary)
                )
            }
            .buttonStyle(.plain)

            Button(action: onBringYourOwnKeys) {
              Text("Bring your own keys")
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(OmiColors.purplePrimary)
                .frame(maxWidth: .infinity)
                .frame(height: 32)
            }
            .buttonStyle(.plain)
          }
          .padding(.horizontal, 24)
        }
        .padding(.bottom, 28)
      }
      .frame(width: 380)
      .background(
        RoundedRectangle(cornerRadius: 16)
          .fill(OmiColors.backgroundRaised)
          .overlay(
            RoundedRectangle(cornerRadius: 16)
              .stroke(OmiColors.border, lineWidth: 1)
          )
      )
      .shadow(color: .black.opacity(0.5), radius: 24, y: 8)
    }
    .transition(.opacity.animation(.easeInOut(duration: 0.2)))
  }
}

#Preview {
  UsageLimitPopupView(
    reason: "transcription",
    onUpgrade: {},
    onDismiss: {},
    onBringYourOwnKeys: {}
  )
  .frame(width: 900, height: 600)
}
