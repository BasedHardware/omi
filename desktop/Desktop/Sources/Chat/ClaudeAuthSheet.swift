import SwiftUI

/// Sheet shown when chat access requires a paid upgrade.
struct ClaudeAuthSheet: View {
    let onConnect: () -> Void
    let onCancel: () -> Void

    @State private var isConnecting = false

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Upgrade to Nooto Pro")
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(NootoColors.textPrimary)

                Spacer()

                Button(action: onCancel) {
                    Image(systemName: "xmark")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(NootoColors.textTertiary)
                        .frame(width: 28, height: 28)
                        .background(NootoColors.backgroundTertiary.opacity(0.5))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 24)
            .padding(.top, 20)
            .padding(.bottom, 16)

            Divider()
                .foregroundColor(NootoColors.border)

            // Content
            VStack(spacing: 20) {
                // Icon
                Image(systemName: "crown")
                    .scaledFont(size: 40)
                    .foregroundColor(NootoColors.textSecondary)
                    .padding(.top, 8)

                // Description
                VStack(spacing: 8) {
                    Text("Unlock Nooto Pro for $199/month")
                        .scaledFont(size: 15, weight: .medium)
                        .foregroundColor(NootoColors.textPrimary)
                        .multilineTextAlignment(.center)

                    Text("Your browser will open to the Nooto Pro checkout. After subscribing, return to Nooto.")
                        .scaledFont(size: 13)
                        .foregroundColor(NootoColors.textTertiary)
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
                            .foregroundColor(NootoColors.textTertiary)
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
                        Text(isConnecting ? "Opening checkout..." : "Upgrade to Nooto Pro")
                            .scaledFont(size: 14, weight: .semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(isConnecting ? NootoColors.backgroundTertiary : Color.accentColor)
                    .foregroundColor(isConnecting ? NootoColors.textSecondary : .white)
                    .cornerRadius(8)
                }
                .buttonStyle(.plain)
                .disabled(isConnecting)

                Button(action: onCancel) {
                    Text("Cancel")
                        .scaledFont(size: 13)
                        .foregroundColor(NootoColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 20)
        }
        .frame(width: 400, height: 380)
        .background(NootoColors.backgroundPrimary)
    }
}
