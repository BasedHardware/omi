import SwiftUI

struct SignInView: View {
    @ObservedObject var authState: AuthState

    var body: some View {
        ZStack {
            // Full background
            OmiColors.backgroundPrimary
                .ignoresSafeArea()

            // Centered sign in card
            VStack(spacing: 32) {
                Spacer()

                // Logo/Title
                VStack(spacing: 16) {
                    // Omi logo
                    if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
                       let logoImage = NSImage(contentsOf: logoURL) {
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
                VStack(spacing: 12) {
                    // Sign in with Apple
                    Button(action: {
                        Task {
                            do {
                                try await AuthService.shared.signInWithApple()
                            } catch {
                                let errorMsg = "Error: \(error.localizedDescription)"
                                authState.error = errorMsg
                                NSLog("OMI Sign in error: %@", errorMsg)
                            }
                        }
                    }) {
                        HStack(spacing: 8) {
                            Image(systemName: "applelogo")
                                .scaledFont(size: 18)
                            Text("Sign in with Apple")
                                .scaledFont(size: 17, weight: .medium)
                        }
                        .foregroundColor(.black)
                        .frame(maxWidth: .infinity)
                        .frame(height: 50)
                        .background(Color.white)
                        .cornerRadius(10)
                    }
                    .buttonStyle(.plain)
                    .disabled(authState.isLoading)

                    // Sign in with Google
                    Button(action: {
                        Task {
                            do {
                                try await AuthService.shared.signInWithGoogle()
                            } catch {
                                let errorMsg = "Error: \(error.localizedDescription)"
                                authState.error = errorMsg
                                NSLog("OMI Sign in error: %@", errorMsg)
                            }
                        }
                    }) {
                        HStack(spacing: 8) {
                            GoogleLogo()
                                .frame(width: 18, height: 18)
                            Text("Sign in with Google")
                                .scaledFont(size: 17, weight: .medium)
                        }
                        .foregroundColor(.black)
                        .frame(maxWidth: .infinity)
                        .frame(height: 50)
                        .background(Color.white)
                        .cornerRadius(10)
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .stroke(Color.gray.opacity(0.3), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(authState.isLoading)

                    // Loading overlay for both buttons
                    if authState.isLoading {
                        ProgressView()
                            .progressViewStyle(CircularProgressViewStyle(tint: OmiColors.textPrimary))
                            .padding(.top, 8)
                    }

                    if let error = authState.error {
                        Text(error)
                            .font(.caption)
                            .foregroundColor(OmiColors.error)
                            .multilineTextAlignment(.center)
                            .padding(.top, 4)
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
           let image = NSImage(contentsOf: url) {
            Image(nsImage: image)
                .resizable()
                .aspectRatio(contentMode: .fit)
        }
    }
}

#Preview {
    SignInView(authState: AuthState.shared)
}
