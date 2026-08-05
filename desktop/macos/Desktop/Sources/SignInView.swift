import AppKit
import OmiTheme
import SwiftUI

/// The first screen anyone ever sees, and therefore the one that has to be most obviously *this*
/// product rather than a template.
///
/// **It paints no ground.** There was a full-bleed dune photograph here under a black gradient, and
/// it is gone rather than restyled: the window wears the glass (`DesktopHomeView.glassShellGround`,
/// "the one ground in this window — nothing above it paints a background"), so an opaque image on top
/// of it hid the panel entirely and forced every label on this screen to be white. White type is what
/// made this the worst-affected screen in the light conversion — it survived only *because* the art
/// under it was dark. The blurred desktop is the backdrop now, the mark and the sentence are the
/// design, and the whole screen is two rungs of near-black type on glass.
struct SignInView: View {
  @ObservedObject var authState: AuthState
  @State private var breathe = false
  /// Sign-in opens on just the Omi mark + wordmark; after a beat the mark spins,
  /// the "Omi" wordmark fades, and the rest of the screen reveals.
  @State private var introRevealed = false

  var body: some View {
    // Clean, centered, symmetric sign-in: brand on the glass, one primary capsule and one secondary,
    // generous whitespace, no floating box and no second ground.
    VStack(spacing: 0) {
      HStack(spacing: 12) {
        SBLogo(size: introRevealed ? 44 : 60, spinning: !introRevealed)
          .scaleEffect(breathe ? 1.04 : 1.0)
          .animation(InkReduceMotion.animation(SBMotion.breathe), value: breathe)

        if !introRevealed {
          Text("Omi")
            .inkStyle(InkType.introHero, color: Ink.primary)
            .transition(.opacity)
        }
      }

      if introRevealed {
        Group {
          Text("A second brain you trust\nmore than your first")
            .inkStyle(InkType.introHero, color: Ink.primary)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.top, InkLayout.rhythm[0])

          Text("It remembers every conversation — and does the follow-ups.")
            .inkStyle(InkType.prose, color: Ink.secondary)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.top, InkLayout.rhythm[5])

          VStack(spacing: InkLayout.rhythm[6]) {
            signInButton(
              title: "Continue with Apple",
              kind: .primary,
              leading: { Image(systemName: "applelogo").font(.system(size: 13)) },
              action: { signIn(apple: true) })
            signInButton(
              title: "Continue with Google",
              kind: .secondary,
              leading: { GoogleLogo().frame(width: 15, height: 15) },
              action: { signIn(apple: false) })
          }
          // This used to be a fixed 320pt column. When the window was
          // narrower (or its usable width was reduced by window chrome),
          // both sign-in actions extended past the visible content area.
          .frame(maxWidth: 320)
          .frame(maxWidth: .infinity)
          .padding(.top, InkLayout.rhythm[0])

          if authState.isLoading {
            HStack(spacing: InkLayout.rhythm[5]) {
              // `Ink.primary`, not a wash: a spinner nobody can see is a screen that looks frozen.
              ProgressView().scaleEffect(0.7).tint(Ink.primary)
              Button {
                AuthService.shared.cancelSignIn()
              } label: {
                Text("Cancel").inkStyle(InkType.statusLabel, color: Ink.secondary)
              }
              .buttonStyle(.plain)
            }
            .padding(.top, InkLayout.rhythm[3])
          }
          if let error = authState.error {
            // The one place this screen raises its voice. It used to be set in the same grey as the
            // footer, which is a failed sign-in reported as a footnote.
            Text(UserFacingErrorPresentation.message(from: error, while: .signIn))
              .inkStyle(InkType.statusLabel, color: Ink.errorRed)
              .multilineTextAlignment(.center)
              .fixedSize(horizontal: false, vertical: true)
              .frame(maxWidth: 320)
              .frame(maxWidth: .infinity)
              .padding(.top, InkLayout.rhythm[4])
          }

          // `secondary` and not a fainter grey: glass carries two rungs, and the bottom one is this.
          Text("open source · runs on your mac · pause anytime")
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
            .padding(.top, InkLayout.rhythm[0])
        }
        .transition(.opacity)
      }
    }
    .onboardingColumn()
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .animation(InkReduceMotion.animation(.easeOut(duration: 0.5)), value: introRevealed)
    // Pins the panel's light appearance, so `Ink`'s dynamic colours resolve dark here even when the
    // machine is in Dark Mode. Without it this screen is near-white type on a near-white panel.
    .glassContent()
    .onAppear {
      breathe = true
      guard !introRevealed else { return }
      DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) {
        InkReduceMotion.perform(.easeOut(duration: 0.5)) { introRevealed = true }
      }
    }
  }

  /// One sign-in action. A **full stadium capsule** from the design system's one button style — the
  /// 12 pt rounded rectangle it replaces was the shape that read as a web form.
  ///
  /// The leading glyph takes no colour of its own: `InkButtonStyle` sets the label, so the Apple mark
  /// inverts with the fill it sits on. `GoogleLogo` is a multicolour bitmap and is unaffected by the
  /// tint, which is correct — it is a third-party mark, not our ink.
  @ViewBuilder private func signInButton<Leading: View>(
    title: String, kind: InkButton.Kind, @ViewBuilder leading: () -> Leading,
    action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      HStack(spacing: 8) {
        leading()
        Text(title)
      }
      .frame(maxWidth: .infinity)
    }
    .buttonStyle(InkButtonStyle(kind: kind))
    .disabled(authState.isLoading)
  }

  private func signIn(apple: Bool) {
    Task {
      do {
        if apple {
          try await AuthService.shared.signInWithApple()
        } else {
          try await AuthService.shared.signInWithGoogle()
        }
      } catch is CancellationError {
      } catch AuthError.cancelled {
      } catch {
        let errorMsg = UserFacingErrorPresentation.message(for: error, while: .signIn)
        authState.error = errorMsg
        NSLog("OMI Sign in error: %@", errorMsg)
      }
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
