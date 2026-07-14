import SwiftUI
import OmiTheme

/// Sheet shown when chat access requires a paid upgrade.
struct ClaudeAuthSheet: View {
    let onConnect: () -> Void
    let onCancel: () -> Void

    @State private var isConnecting = false

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Upgrade to Omi Pro")
                    .scaledFont(size: OmiType.heading, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: onCancel) {
                    Image(systemName: "xmark")
                        .scaledFont(size: OmiType.body, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 28, height: 28)
                        .background(OmiColors.backgroundTertiary.opacity(0.5))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, OmiSpacing.xxl)
            .padding(.top, OmiSpacing.xl)
            .padding(.bottom, OmiSpacing.lg)

            Divider()
                .foregroundColor(OmiColors.border)

            // Content
            VStack(spacing: OmiSpacing.xl) {
                // Icon
                Image(systemName: "crown")
                    .scaledFont(size: OmiType.hero)
                    .foregroundColor(OmiColors.textSecondary)
                    .padding(.top, OmiSpacing.sm)

                // Description
                VStack(spacing: OmiSpacing.sm) {
                    Text("Unlock Omi Pro for $199/month")
                        .scaledFont(size: OmiType.subheading, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                        .multilineTextAlignment(.center)

                    Text("Your browser will open to the Omi Pro checkout. After subscribing, return to omi.")
                        .scaledFont(size: OmiType.body)
                        .foregroundColor(OmiColors.textTertiary)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.horizontal, OmiSpacing.xl)

                if isConnecting {
                    VStack(spacing: OmiSpacing.md) {
                        ProgressView()
                            .controlSize(.small)

                        Text("Complete sign-in in your browser...")
                            .scaledFont(size: OmiType.body)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .padding(.top, OmiSpacing.xxs)
                }
            }
            .padding(.horizontal, OmiSpacing.xxl)
            .padding(.vertical, OmiSpacing.lg)

            Spacer()

            // Actions
            VStack(spacing: OmiSpacing.md) {
                Button(action: {
                    isConnecting = true
                    onConnect()
                }) {
                    HStack(spacing: OmiSpacing.sm) {
                        if isConnecting {
                            ProgressView()
                                .controlSize(.mini)
                        }
                        Text(isConnecting ? "Opening checkout..." : "Upgrade to Omi Pro")
                            .scaledFont(size: OmiType.body, weight: .semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, OmiSpacing.sm)
                    .background(isConnecting ? OmiColors.backgroundTertiary : Color.accentColor)
                    .foregroundColor(isConnecting ? OmiColors.textSecondary : OmiColors.backgroundPrimary)
                    .cornerRadius(OmiChrome.elementRadius)
                }
                .buttonStyle(.plain)
                .disabled(isConnecting)

                Button(action: onCancel) {
                    Text("Cancel")
                        .scaledFont(size: OmiType.body)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, OmiSpacing.xxl)
            .padding(.bottom, OmiSpacing.xl)
        }
        .frame(width: 400, height: 380)
        .background(OmiColors.backgroundPrimary)
    }
}
