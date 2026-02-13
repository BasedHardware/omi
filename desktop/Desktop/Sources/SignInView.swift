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
                    if let logoImage = NSImage(contentsOf: Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png")!) {
                        Image(nsImage: logoImage)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(width: 64, height: 64)
                    }

                    Text("Omi")
                        .font(.system(size: 48, weight: .bold))
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
                                .font(.system(size: 18))
                            Text("Sign in with Apple")
                                .font(.system(size: 17, weight: .medium))
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
                            // Google "G" logo using SF Symbol or text
                            Text("G")
                                .font(.system(size: 20, weight: .bold))
                                .foregroundStyle(
                                    LinearGradient(
                                        colors: [.blue, .green, .yellow, .red],
                                        startPoint: .topLeading,
                                        endPoint: .bottomTrailing
                                    )
                                )
                            Text("Sign in with Google")
                                .font(.system(size: 17, weight: .medium))
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

#Preview {
    SignInView(authState: AuthState.shared)
}
