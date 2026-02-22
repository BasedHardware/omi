import SwiftUI

/// Sheet shown when ACP bridge (Mode B) requires the user to authenticate
/// with their Claude account via OAuth.
struct ClaudeAuthSheet: View {
    let onConnect: () -> Void
    let onCancel: () -> Void

    @State private var isConnecting = false

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Connect Your Claude Account")
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: onCancel) {
                    Image(systemName: "xmark")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 28, height: 28)
                        .background(OmiColors.backgroundTertiary.opacity(0.5))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 24)
            .padding(.top, 20)
            .padding(.bottom, 16)

            Divider()
                .foregroundColor(OmiColors.border)

            // Content
            VStack(spacing: 20) {
                // Icon
                Image(systemName: "person.badge.key")
                    .scaledFont(size: 40)
                    .foregroundColor(OmiColors.textSecondary)
                    .padding(.top, 8)

                // Description
                VStack(spacing: 8) {
                    Text("Use your own Claude Pro or Max subscription")
                        .scaledFont(size: 15, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                        .multilineTextAlignment(.center)

                    Text("You'll be redirected to claude.ai to sign in. Your Omi conversations will use your Claude account's API quota.")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.horizontal, 20)

                if isConnecting {
                    VStack(spacing: 12) {
                        ProgressView()
                            .controlSize(.small)

                        Text("Complete sign-in in your browser...")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .padding(.top, 4)
                }
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 16)

            Spacer()

            // Actions
            VStack(spacing: 12) {
                Button(action: {
                    isConnecting = true
                    onConnect()
                }) {
                    HStack(spacing: 8) {
                        if isConnecting {
                            ProgressView()
                                .controlSize(.mini)
                        }
                        Text(isConnecting ? "Waiting for sign-in..." : "Connect Claude Account")
                            .scaledFont(size: 14, weight: .semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(isConnecting ? OmiColors.backgroundTertiary : Color.accentColor)
                    .foregroundColor(isConnecting ? OmiColors.textSecondary : .white)
                    .cornerRadius(8)
                }
                .buttonStyle(.plain)
                .disabled(isConnecting)

                Button(action: onCancel) {
                    Text("Cancel")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 20)
        }
        .frame(width: 400, height: 380)
        .background(OmiColors.backgroundPrimary)
    }
}
