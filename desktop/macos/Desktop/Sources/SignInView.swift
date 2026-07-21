import AppKit
import OmiTheme
import SwiftUI

struct SignInView: View {
  @ObservedObject var authState: AuthState
  @Environment(\.sbTheme) private var sb
  @State private var breathe = false

  private static let logoImage: NSImage? = {
    guard let url = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
      let data = try? Data(contentsOf: url)
    else { return nil }
    let img = NSImage(data: data)
    img?.isTemplate = true
    return img
  }()

  private static let backgroundImage: NSImage? = {
    guard let url = Bundle.resourceBundle.url(forResource: "signin_bg", withExtension: "png") else { return nil }
    return NSImage(contentsOf: url)
  }()

  var body: some View {
    ZStack {
      // Sign-in background image, dimmed under the content for legibility.
      if let bg = Self.backgroundImage {
        Image(nsImage: bg)
          .resizable()
          .scaledToFill()
          .overlay(
            LinearGradient(
              colors: [.black.opacity(0.32), .black.opacity(0.42), .black.opacity(0.66)],
              startPoint: .top, endPoint: .bottom)
          )
          .frame(maxWidth: .infinity, maxHeight: .infinity)
          .clipped()
          .ignoresSafeArea()
      } else {
        SBWallpaper()
      }

      // Clean, centered, symmetric sign-in — the way premium apps do it:
      // brand on the backdrop, one primary + one frosted-glass secondary button,
      // generous whitespace, no floating box.
      VStack(spacing: 0) {
        HStack(spacing: 12) {
          Group {
            if let logo = Self.logoImage {
              Image(nsImage: logo).resizable().renderingMode(.template).scaledToFit()
            } else {
              Circle().strokeBorder(lineWidth: 5)
            }
          }
          .frame(width: 42, height: 42)

          Text("Omi")
            .geist(size: 34, weight: .semibold, tracking: 34 * -0.02)
        }
        .foregroundStyle(sb.ink)
        .scaleEffect(breathe ? 1.08 : 1.0)
        .opacity(breathe ? 1.0 : 0.85)
        .animation(SBMotion.breathe, value: breathe)

        Text("A second brain you trust\nmore than your first")
          .geist(size: 32, weight: .semibold, tracking: 32 * -0.03)
          .foregroundStyle(sb.ink)
          .multilineTextAlignment(.center)
          .lineSpacing(3)
          .fixedSize(horizontal: false, vertical: true)
          .padding(.top, 28)

        Text("It remembers every conversation — and does the follow-ups.")
          .geist(size: 15)
          .foregroundStyle(sb.ink(.w55))
          .multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)
          .padding(.top, 10)

        VStack(spacing: 11) {
          signInButton(
            title: "Continue with Apple",
            filled: true,
            leading: {
              Image(systemName: "applelogo").font(.system(size: 13)).foregroundStyle(sb.inkInverted)
            },
            action: { signIn(apple: true) })
          signInButton(
            title: "Continue with Google",
            filled: false,
            leading: { GoogleLogo().frame(width: 15, height: 15) },
            action: { signIn(apple: false) })
        }
        .frame(width: 320)
        .padding(.top, 34)

        if authState.isLoading {
          HStack(spacing: 10) {
            ProgressView().scaleEffect(0.7).tint(sb.ink(.w6))
            Button { AuthService.shared.cancelSignIn() } label: {
              Text("Cancel").geist(size: 12.5).foregroundStyle(sb.ink(.w45))
            }
            .buttonStyle(.plain)
          }
          .padding(.top, 14)
        }
        if let error = authState.error {
          Text(UserFacingErrorPresentation.message(from: error, while: .signIn))
            .geist(size: 12.5).foregroundStyle(sb.ink(.w6))
            .multilineTextAlignment(.center)
            .frame(width: 320)
            .padding(.top, 12)
        }

        Text("open source · runs on your mac · pause anytime")
          .geistMono(size: 12)
          .foregroundStyle(sb.ink(.w35))
          .padding(.top, 28)
      }
      .frame(maxWidth: 460)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .onAppear { breathe = true }
  }

  @ViewBuilder private func signInButton<Leading: View>(
    title: String, filled: Bool, @ViewBuilder leading: () -> Leading, action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      HStack(spacing: 8) {
        leading()
        Text(title).geist(size: 15, weight: filled ? .semibold : .medium)
      }
      .foregroundStyle(filled ? sb.inkInverted : sb.ink(.w9))
      .frame(maxWidth: .infinity)
      .padding(.vertical, 12.5)
      .background(buttonBackground(filled: filled))
      .overlay(
        RoundedRectangle(cornerRadius: 12, style: .continuous)
          .stroke(filled ? .clear : Color.white.opacity(0.16), lineWidth: 1)
      )
    }
    .buttonStyle(.plain)
    .disabled(authState.isLoading)
  }

  @ViewBuilder private func buttonBackground(filled: Bool) -> some View {
    let shape = RoundedRectangle(cornerRadius: 12, style: .continuous)
    if filled {
      shape.fill(sb.ink)
    } else {
      shape.fill(Color.white.opacity(0.08))
        .background(.ultraThinMaterial, in: shape)
    }
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
