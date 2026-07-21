import OmiTheme
import SwiftUI

struct SignInView: View {
  @ObservedObject var authState: AuthState

  var body: some View {
    ZStack {
      // Full background
      OmiColors.backgroundPrimary
        .ignoresSafeArea()

      // Centered sign in card
      VStack(spacing: OmiSpacing.section) {
        Spacer()

        // Logo/Title
        VStack(spacing: OmiSpacing.lg) {
          // Omi logo
          if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
            let logoImage = NSImage(contentsOf: logoURL)
          {
            Image(nsImage: logoImage)
              .resizable()
              .aspectRatio(contentMode: .fit)
              .frame(width: 64, height: 64)
          }

          Text("omi")
            .scaledFont(size: 48, weight: .bold)
            .foregroundColor(OmiColors.textPrimary)

          Text("Sign in to continue")
            .font(.title3)
            .foregroundColor(OmiColors.textTertiary)
        }

        Spacer()

        // Sign in buttons
        VStack(spacing: OmiSpacing.md) {
          // Sign in with Apple
          Button(action: {
            Task {
              do {
                try await AuthService.shared.signInWithApple()
              } catch is CancellationError {
                // swallow — user initiated
              } catch AuthError.cancelled {
                // swallow — user initiated
              } catch {
                let errorMsg = UserFacingErrorPresentation.message(for: error, while: .signIn)
                authState.error = errorMsg
                NSLog("OMI Sign in error: %@", errorMsg)
              }
            }
          }) {
            HStack(spacing: OmiSpacing.sm) {
              Image(systemName: "applelogo")
                .scaledFont(size: OmiType.heading)
              Text("Sign in with Apple")
                .scaledFont(size: OmiType.subheading, weight: .medium)
            }
            .foregroundColor(.black)
            .frame(maxWidth: .infinity)
            .frame(height: 50)
            .background(Color.white)
            .cornerRadius(OmiChrome.smallControlRadius)
          }
          .buttonStyle(.plain)
          .disabled(authState.isLoading)

          // Sign in with Google
          Button(action: {
            Task {
              do {
                try await AuthService.shared.signInWithGoogle()
              } catch is CancellationError {
                // swallow — user initiated
              } catch AuthError.cancelled {
                // swallow — user initiated
              } catch {
                let errorMsg = UserFacingErrorPresentation.message(for: error, while: .signIn)
                authState.error = errorMsg
                NSLog("OMI Sign in error: %@", errorMsg)
              }
            }
          }) {
            HStack(spacing: OmiSpacing.sm) {
              GoogleLogo()
                .frame(width: 18, height: 18)
              Text("Sign in with Google")
                .scaledFont(size: OmiType.subheading, weight: .medium)
            }
            .foregroundColor(.black)
            .frame(maxWidth: .infinity)
            .frame(height: 50)
            .background(Color.white)
            .cornerRadius(OmiChrome.smallControlRadius)
            .overlay(
              RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                .stroke(Color.gray.opacity(0.3), lineWidth: 1)
            )
          }
          .buttonStyle(.plain)
          .disabled(authState.isLoading)

          // Loading overlay for both buttons
          if authState.isLoading {
            ProgressView()
              .progressViewStyle(CircularProgressViewStyle(tint: OmiColors.textPrimary))
              .padding(.top, OmiSpacing.sm)

            // Minimal escape hatch so a failed web sign-in (closed tab,
            // denied on Apple/Google, etc.) doesn't trap the user with
            // permanently disabled buttons waiting for a callback that
            // will never arrive.
            Button(action: {
              AuthService.shared.cancelSignIn()
            }) {
              Text("Cancel")
                .font(.caption)
                .foregroundColor(OmiColors.textTertiary)
            }
            .buttonStyle(.plain)
            .padding(.top, OmiSpacing.xxs)
          }

          if let error = authState.error {
            Text(UserFacingErrorPresentation.message(from: error, while: .signIn))
              .font(.caption)
              .foregroundColor(OmiColors.error)
              .multilineTextAlignment(.center)
              .padding(.top, OmiSpacing.xxs)
          }
        }
        .frame(width: 320)

        Spacer()
          .frame(height: 60)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
  }
}

// MARK: - Google Logo

/// Standard multicolor Google "G" logo
struct GoogleLogo: View {
  var body: some View {
    if let url = Bundle.resourceBundle.url(forResource: "google_logo", withExtension: "png"),
      let image = NSImage(contentsOf: url)
    {
      Image(nsImage: image)
        .resizable()
        .aspectRatio(contentMode: .fit)
    }
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    SignInView(authState: AuthState.shared)
  }
#endif
