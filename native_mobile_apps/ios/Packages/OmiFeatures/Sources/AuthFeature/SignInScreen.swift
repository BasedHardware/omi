import AuthenticationServices
import CryptoKit
import OmiDesign
import OmiService
import SwiftUI

/// First screen for signed-out users. Apple/Google sign-in arrive with onboarding (P6); the
/// local harness signs in through the backend's custom-token endpoint, like the Flutter dev flavor.
public struct SignInScreen: View {
    @Environment(SessionStore.self) private var session
    @State private var devUserID = "local-dev-user"
    @State private var appleNonce = ""
    /// Google's sheet lives in the app target (GoogleSignIn SDK); nil hides the button.
    private let googleSignIn: (() async throws -> ProviderCredential)?

    public init(googleSignIn: (() async throws -> ProviderCredential)?) {
        self.googleSignIn = googleSignIn
    }

    public var body: some View {
        ZStack(alignment: .bottom) {
            PhotoReel()
            VStack(spacing: DS.Spacing.xl) {
                VStack(spacing: DS.Spacing.sm) {
                    Text("omi")
                        .font(.system(size: 64, weight: .bold))
                        .accessibilityLabel("Omi")
                    Text(L("captureEveryMoment"))
                        .font(DS.Typography.body)
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .multilineTextAlignment(.center)
                }
                VStack(spacing: DS.Spacing.sm) {
                    appleButton
                    if let googleSignIn {
                        Button {
                            Task {
                                guard let credential = try? await googleSignIn() else { return }
                                await session.signIn(with: credential)
                            }
                        } label: {
                            Label(L("signInWithGoogle"), systemImage: "g.circle.fill")
                                .font(DS.Typography.button)
                                .foregroundStyle(DS.Palette.ink)
                                .frame(maxWidth: .infinity, minHeight: DS.Size.primaryButtonHeight)
                                .omiSurface(Capsule(), interactive: true)
                        }
                        .buttonStyle(.plain)
                    }
                    if session.canUseLocalDevSignIn { localDevSignIn }
                    if let error = session.errorMessage {
                        Text(error)
                            .font(DS.Typography.caption)
                            .foregroundStyle(DS.Palette.live)
                            .multilineTextAlignment(.center)
                    }
                    Text(.init(
                        L("byContinuingAgree") + "[\(L("privacyPolicy"))](https://www.omi.me/pages/privacy)" + L("and")
                            + "[\(L("termsOfUse"))](https://www.omi.me/pages/terms-of-service)."
                    ))
                    .font(DS.Typography.micro)
                    .foregroundStyle(DS.Palette.inkTertiary)
                    .tint(DS.Palette.inkSecondary)
                    .multilineTextAlignment(.center)
                    .padding(.top, DS.Spacing.xs)
                }
            }
            .padding(.horizontal, DS.Spacing.gutter)
            .padding(.bottom, DS.Spacing.md)
        }
        .background(DS.Palette.background)
        .environment(\.colorScheme, .dark)
    }

    private var localDevSignIn: some View {
        VStack(spacing: DS.Spacing.sm) {
            Picker(L("nativeLocalUser"), selection: $devUserID) {
                Text("local-dev-user").tag("local-dev-user")
                Text("alice").tag("alice")
                Text("bob").tag("bob")
            }
            .pickerStyle(.segmented)
            Button {
                Task { await session.signInLocalDev(uid: devUserID) }
            } label: {
                HStack {
                    if session.isWorking { ProgressView() }
                    Text(L("nativeLocalSignIn"))
                }
            }
            .buttonStyle(.omiSecondary)
            .disabled(session.isWorking)
            .accessibilityIdentifier("signin.localDev")
        }
    }

    /// Sign in with Apple, same nonce scheme as the Flutter app (SHA-256 of a random raw nonce).
    private var appleButton: some View {
        SignInWithAppleButton(.signIn) { request in
            appleNonce = Self.randomNonce()
            request.requestedScopes = [.fullName, .email]
            request.nonce = Self.sha256(appleNonce)
        } onCompletion: { result in
            guard case let .success(authorization) = result,
                  let apple = authorization.credential as? ASAuthorizationAppleIDCredential,
                  let tokenData = apple.identityToken,
                  let token = String(data: tokenData, encoding: .utf8) else { return }
            let credential = ProviderCredential.apple(
                idToken: token, rawNonce: appleNonce,
                givenName: apple.fullName?.givenName, familyName: apple.fullName?.familyName
            )
            Task { await session.signIn(with: credential) }
        }
        .signInWithAppleButtonStyle(.white)
        .frame(height: DS.Size.primaryButtonHeight)
        .clipShape(Capsule())
        .accessibilityIdentifier("signin.apple")
    }

    static func randomNonce(length: Int = 32) -> String {
        let charset = Array("0123456789ABCDEFGHIJKLMNOPQRSTUVXYZabcdefghijklmnopqrstuvwxyz-._")
        var generator = SystemRandomNumberGenerator()
        return String((0 ..< length).map { _ in charset[Int.random(in: 0 ..< charset.count, using: &generator)] })
    }

    static func sha256(_ input: String) -> String {
        SHA256.hash(data: Data(input.utf8)).map { String(format: "%02x", $0) }.joined()
    }
}

/// Omi's onboarding photos, slowly drifting and cross-fading, darkened toward the bottom.
struct PhotoReel: View {
    @State private var index = 0
    @State private var drift = false
    private let photos = OmiMedia.Background.allCases

    var body: some View {
        GeometryReader { proxy in
            ZStack {
                ForEach(Array(photos.enumerated()), id: \.offset) { offset, photo in
                    OmiMedia.background(photo)
                        .resizable()
                        .scaledToFill()
                        .frame(width: proxy.size.width, height: proxy.size.height * 0.75, alignment: .top)
                        .scaleEffect(drift && offset == index ? 1.08 : 1, anchor: .top)
                        .clipped()
                        .opacity(offset == index ? 1 : 0)
                }
            }
            .frame(maxHeight: .infinity, alignment: .top)
            .overlay {
                LinearGradient(
                    stops: [
                        .init(color: .black.opacity(0.3), location: 0),
                        .init(color: .clear, location: 0.2),
                        .init(color: .black.opacity(0.75), location: 0.55),
                        .init(color: .black, location: 0.72),
                    ],
                    startPoint: .top, endPoint: .bottom
                )
            }
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
        .task {
            withAnimation(.linear(duration: 6)) { drift = true }
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                drift = false
                withAnimation(.easeInOut(duration: 1.2)) { index = (index + 1) % photos.count }
                withAnimation(.linear(duration: 6)) { drift = true }
            }
        }
    }
}
