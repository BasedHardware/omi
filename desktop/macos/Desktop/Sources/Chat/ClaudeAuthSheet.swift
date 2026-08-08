import OmiTheme
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
        Text("Upgrade to Omi Pro")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(Ink.primary)

        Spacer()

        Button(action: onCancel) {
          Image(systemName: "xmark")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.secondary)
            .frame(width: 28, height: 28)
            .background(Ink.rowFillHover)
            .clipShape(Circle())
        }
        .buttonStyle(.plain)
      }
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.top, OmiSpacing.xl)
      .padding(.bottom, OmiSpacing.lg)

      GlassSeparator()

      // Content
      VStack(spacing: OmiSpacing.xl) {
        // Icon
        Image(systemName: "crown")
          .scaledFont(size: OmiType.hero)
          .foregroundColor(Ink.secondary)
          .padding(.top, OmiSpacing.sm)

        // Description
        VStack(spacing: OmiSpacing.sm) {
          Text("Unlock Omi Pro for $199/month")
            .scaledFont(size: OmiType.subheading, weight: .medium)
            .foregroundColor(Ink.primary)
            .multilineTextAlignment(.center)

          Text("Your browser will open to the Omi Pro checkout. After subscribing, return to omi.")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
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
              .foregroundColor(Ink.secondary)
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
        }
        // The shared primary action, which is a stadium and gives on press by opacity alone.
        //
        // This replaces a hand-rolled `Color.accentColor` fill — an INV-UI-1 violation rather than
        // a style choice: macOS lets a user pick the banned hue as their system accent, so
        // `accentColor` renders off-brand on those machines and no pixel check would catch it.
        // `InkButtonStyle` also drops the in-flight colour fork entirely: it dims a disabled button
        // itself, so the two colour pairs this used to carry are down to none.
        .buttonStyle(InkButtonStyle(kind: .primary))
        .disabled(isConnecting)

        Button(action: onCancel) {
          Text("Cancel")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
        }
        .buttonStyle(.plain)
      }
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.bottom, OmiSpacing.xl)
    }
    .frame(width: 400, height: 380)
    // A sheet is its own window, not content hosted on the panel, so this is one of the few places
    // that *should* paint a ground — and `glassContent()` pins the light appearance it resolves in,
    // which a sheet does not inherit from the panel that presented it.
    .background(Ink.surface)
    .glassContent()
  }
}
