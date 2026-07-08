import SwiftUI

/// Redesigned sign-in — mockup `signin.html`. Warm-paper, centered, serif wordmark.
///
/// Drop-in replacement for `SignInView`: same initializer (`authState:`) and it
/// reuses the SAME real sign-in actions — `AuthService.shared.signInWithApple()`,
/// `AuthService.shared.signInWithGoogle()`, and `AuthService.shared.cancelSignIn()`.
struct RedesignSignInView: View {
  @ObservedObject var authState: AuthState

  var body: some View {
    ZStack {
      Ink.canvas.ignoresSafeArea()

      // Scarce warm glow at the top, matching the mockup's radial wash.
      LinearGradient(
        colors: [Color(hex: 0xE0A82E, alpha: 0.06), .clear],
        startPoint: .top, endPoint: .center
      )
      .ignoresSafeArea()

      VStack(spacing: 0) {
        Spacer()

        // Wordmark + tagline (both serif).
        Text("omi")
          .font(InkFont.serif(64, .medium))
          .foregroundColor(Ink.ink)
          .tracking(-2.5)

        Text("A second brain you trust more than your first.")
          .font(InkFont.serif(22, .regular))
          .foregroundColor(Ink.body)
          .tracking(-0.2)
          .multilineTextAlignment(.center)
          .frame(maxWidth: 380)
          .padding(.top, 22)

        // Auth buttons — the REAL sign-in actions.
        VStack(spacing: 12) {
          authButton(kind: .primary, action: signInWithApple) {
            Image(systemName: "applelogo")
              .font(.system(size: 16, weight: .medium))
            Text("Continue with Apple")
          }

          authButton(kind: .plain, action: signInWithGoogle) {
            GoogleLogo().frame(width: 16, height: 16)
            Text("Continue with Google")
          }
        }
        .frame(width: 300)
        .padding(.top, InkSpace.s7)
        .disabled(authState.isLoading)
        .opacity(authState.isLoading ? 0.6 : 1)

        // Loading + escape hatch (mirrors SignInView so a failed web
        // sign-in doesn't trap the user waiting on a callback).
        if authState.isLoading {
          ProgressView()
            .progressViewStyle(CircularProgressViewStyle(tint: Ink.ink))
            .padding(.top, 16)
          Button(action: { AuthService.shared.cancelSignIn() }) {
            Text("Cancel").font(InkFont.sans(12)).foregroundColor(Ink.faint)
          }
          .buttonStyle(.plain)
          .padding(.top, 6)
        }

        if let error = authState.error {
          Text(error)
            .font(InkFont.sans(12))
            .foregroundColor(Ink.danger)
            .multilineTextAlignment(.center)
            .frame(maxWidth: 300)
            .padding(.top, 12)
        }

        // Source-code caption link.
        Button(action: openSourceCode) {
          HStack(spacing: 8) {
            Image(systemName: "chevron.left.forwardslash.chevron.right")
              .font(.system(size: 11))
            Text("Read the source code ↗").font(InkFont.sans(12))
          }
          .foregroundColor(Ink.muted)
        }
        .buttonStyle(.plain)
        .padding(.top, InkSpace.s6)

        Spacer()
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .padding(60)
    }
  }

  // MARK: Buttons

  @ViewBuilder
  private func authButton<Label: View>(
    kind: InkButtonKind, action: @escaping () -> Void, @ViewBuilder label: () -> Label
  ) -> some View {
    let filled = (kind == .primary || kind == .accent)
    Button(action: action) {
      HStack(spacing: 10) {
        label()
      }
      .font(InkFont.sans(15, .medium))
      .foregroundColor(filled ? Ink.accentInk : Ink.ink)
      .frame(maxWidth: .infinity)
      .frame(height: 46)
      .background(
        Capsule(style: .continuous)
          .fill(filled ? Ink.ink : Ink.surface)
          .overlay(
            Capsule(style: .continuous)
              .strokeBorder(filled ? Color.clear : Ink.hair2, lineWidth: 1))
      )
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
  }

  // MARK: Real sign-in actions (reused from SignInView)

  private func signInWithApple() {
    Task {
      do {
        try await AuthService.shared.signInWithApple()
      } catch is CancellationError {
      } catch AuthError.cancelled {
      } catch {
        let errorMsg = "Error: \(error.localizedDescription)"
        authState.error = errorMsg
        NSLog("OMI Sign in error: %@", errorMsg)
      }
    }
  }

  private func signInWithGoogle() {
    Task {
      do {
        try await AuthService.shared.signInWithGoogle()
      } catch is CancellationError {
      } catch AuthError.cancelled {
      } catch {
        let errorMsg = "Error: \(error.localizedDescription)"
        authState.error = errorMsg
        NSLog("OMI Sign in error: %@", errorMsg)
      }
    }
  }

  private func openSourceCode() {
    if let url = URL(string: "https://github.com/BasedHardware/omi") {
      NSWorkspace.shared.open(url)
    }
  }
}

#if canImport(PreviewsMacros)
#Preview {
  RedesignSignInView(authState: AuthState.shared)
}
#endif
