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
              colors: [.black.opacity(0.5), .black.opacity(0.62), .black.opacity(0.82)],
              startPoint: .top, endPoint: .bottom)
          )
          .frame(maxWidth: .infinity, maxHeight: .infinity)
          .clipped()
          .ignoresSafeArea()
      } else {
        SBWallpaper()
      }

      VStack(spacing: 0) {
        // Breathing logo.
        Group {
          if let logo = Self.logoImage {
            Image(nsImage: logo).resizable().renderingMode(.template).scaledToFit()
          } else {
            Circle().strokeBorder(lineWidth: 5)
          }
        }
        .foregroundStyle(sb.ink)
        .frame(width: 44, height: 44)
        .scaleEffect(breathe ? 1.08 : 1.0)
        .opacity(breathe ? 1.0 : 0.85)
        .animation(SBMotion.breathe, value: breathe)

        Text("A second brain you trust\nmore than your first")
          .geist(size: 36, weight: .semibold, tracking: 36 * -0.03)
          .foregroundStyle(sb.ink)
          .multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)
          .padding(.top, 26)

        Text("It remembers every conversation — and does the follow-ups.")
          .geist(size: 15.5)
          .foregroundStyle(sb.ink(.w45))
          .multilineTextAlignment(.center)
          .padding(.top, 8)

        VStack(spacing: 10) {
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
            leading: { GoogleLogo().frame(width: 14, height: 14) },
            action: { signIn(apple: false) })

          if authState.isLoading {
            ProgressView().scaleEffect(0.7).tint(sb.ink(.w6)).padding(.top, 6)
            Button { AuthService.shared.cancelSignIn() } label: {
              Text("Cancel").geist(size: 12).foregroundStyle(sb.ink(.w4))
            }
            .buttonStyle(.plain)
          }
          if let error = authState.error {
            Text(UserFacingErrorPresentation.message(from: error, while: .signIn))
              .geist(size: 12).foregroundStyle(sb.ink(.w5))
              .multilineTextAlignment(.center).padding(.top, 4)
          }
        }
        .frame(width: 300)
        .padding(.top, 34)

        Text("open source · runs on your mac · pause anytime")
          .geistMono(size: 12)
          .foregroundStyle(sb.ink(.w28))
          .padding(.top, 30)
      }
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
      .foregroundStyle(filled ? sb.inkInverted : sb.ink(.w85))
      .frame(maxWidth: .infinity)
      .padding(.vertical, 11)
      .background(
        RoundedRectangle(cornerRadius: 11, style: .continuous)
          .fill(filled ? sb.ink : sb.ink(.w04))
      )
      .overlay(
        RoundedRectangle(cornerRadius: 11, style: .continuous)
          .stroke(filled ? .clear : sb.ink(.w18), lineWidth: 1)
      )
    }
    .buttonStyle(.plain)
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
