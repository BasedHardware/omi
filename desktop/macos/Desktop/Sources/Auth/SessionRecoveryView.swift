import OmiTheme
import SwiftUI

/// Shown when credentials still exist but launch-time validation could not
/// complete (for example, offline or a temporarily locked Keychain).
/// Authenticated product surfaces remain gated until Retry succeeds.
///
/// It sits in the same auth entry shell as `SignInView` and wears the same card
/// (`onboardingScreen`) — one piece of glass on the desktop, since the window itself has no ground —
/// and spends the same two rungs on it. The glyph and the headline were `.white`, the literal that is
/// invisible on the light panel, and the sentence under them was `.secondary`, AppKit's own step
/// rather than the ladder's, which measures 3.95:1 over this surface and fails AA for body text (see
/// `Ink.secondary`).
struct SessionRecoveryView: View {
  @State private var isRetrying = false

  var body: some View {
    VStack(spacing: InkLayout.rhythm[3]) {
      Image(systemName: "lock.rotation")
        .font(.system(size: 34, weight: .medium))
        .foregroundStyle(Ink.primary)

      Text("We couldn't verify your session")
        .inkStyle(InkType.stepHeadline, color: Ink.primary)
        .multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)

      Text("Your local data and setup are safe. Check your connection and retry, or sign in again.")
        .inkStyle(InkType.prose, color: Ink.secondary)
        .multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: InkLayout.contentMaxWidth)

      // Retry leads, because it is the action that keeps the session. Both are stadium capsules from
      // the one button style — `.bordered` / `.borderedProminent` are AppKit's shapes and colours,
      // which on this panel are a different product's buttons.
      HStack(spacing: InkLayout.rhythm[4]) {
        Button {
          isRetrying = true
          Task {
            await AuthService.shared.retryRestoredSession()
            isRetrying = false
          }
        } label: {
          if isRetrying {
            ProgressView()
              .controlSize(.small)
          } else {
            Text("Retry")
          }
        }
        .buttonStyle(InkButtonStyle(kind: .primary))
        .disabled(isRetrying)
        .accessibilityIdentifier("auth_recovery_retry")

        Button("Sign In Again") {
          Task {
            await AuthService.shared.invalidateSession(reason: .manual)
          }
        }
        .buttonStyle(InkButtonStyle(kind: .secondary))
        .accessibilityIdentifier("auth_recovery_sign_in")
      }
    }
    // Same object as the onboarding card and sign-in: a column on the shared glass, centred on the
    // desktop. It used to be a bare column, which was right while the window carried a full-bleed
    // ground and wrong the moment `ShellWindowChrome` retired one.
    .onboardingScreen()
  }
}
