import SwiftUI

/// Shown when credentials still exist but launch-time validation could not
/// complete (for example, offline or a temporarily locked Keychain).
/// Authenticated product surfaces remain gated until Retry succeeds.
struct SessionRecoveryView: View {
  @State private var isRetrying = false

  var body: some View {
    VStack(spacing: 16) {
      Image(systemName: "lock.rotation")
        .font(.system(size: 34, weight: .medium))
        .foregroundStyle(.white)

      Text("We couldn't verify your session")
        .font(.title3.weight(.semibold))
        .foregroundStyle(.white)

      Text("Your local data and setup are safe. Check your connection and retry, or sign in again.")
        .font(.body)
        .foregroundStyle(.secondary)
        .multilineTextAlignment(.center)
        .frame(maxWidth: 420)

      HStack(spacing: 12) {
        Button("Sign In Again") {
          AuthService.shared.invalidateSession(reason: .manual)
        }
        .buttonStyle(.bordered)
        .accessibilityIdentifier("auth_recovery_sign_in")

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
        .buttonStyle(.borderedProminent)
        .disabled(isRetrying)
        .accessibilityIdentifier("auth_recovery_retry")
      }
    }
    .padding(32)
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }
}
