import SwiftUI

/// Founder-chat help screen — mockup `help.html`, wired to the REAL support chat
/// (`CrispWebView`, the same one `MainWindow/HelpPage.swift` uses).
///
/// Parameterless so it drops straight into `PageContentView` (`RedesignHelpPage()`).
struct RedesignHelpPage: View {
  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Founder header.
      HStack(spacing: 14) {
        ZStack {
          Circle().fill(Ink.fillClay)
          Text("N")
            .font(InkFont.sans(18, .semibold))
            .foregroundColor(.white)
        }
        .frame(width: 52, height: 52)

        VStack(alignment: .leading, spacing: 3) {
          Text("Talk to a founder").inkH2()
          Text("We usually reply fast — send us a message right here.").inkSmall()
        }
        Spacer()

        // Links to the real destinations.
        HStack(spacing: 10) {
          InkButton(title: "Discord", kind: .plain, size: .sm) { open(Self.discordURL) }
          InkButton(title: "Docs", kind: .ghost, size: .sm) { open(Self.docsURL) }
          InkButton(title: "Source ↗", kind: .ghost, size: .sm) { open(Self.sourceURL) }
        }
      }
      .padding(.horizontal, 40)
      .padding(.vertical, 24)

      Rectangle().fill(Ink.hair).frame(height: 1)

      // The real Crisp support chat.
      CrispWebView()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
  }

  // MARK: URLs (the real destinations)

  private static let discordURL = URL(string: "https://discord.com/invite/8MP3b9ymvx")!
  private static let docsURL = URL(string: "https://docs.omi.me")!
  private static let sourceURL = URL(string: "https://github.com/BasedHardware/omi")!

  private func open(_ url: URL) { NSWorkspace.shared.open(url) }
}

#if canImport(PreviewsMacros)
#Preview {
  RedesignHelpPage().frame(width: 900, height: 640)
}
#endif
