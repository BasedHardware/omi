import SwiftUI

/// Founder-chat help screen — mockup `help.html`. Static/light for now; the real
/// Crisp integration (see `MainWindow/HelpPage.swift`) can be wired in later.
///
/// Parameterless so it drops straight into `PageContentView` (`RedesignHelpPage()`),
/// where `appState`, `viewModelContainer`, and `$selectedTabIndex` are in scope but
/// this screen needs none of them.
struct RedesignHelpPage: View {
  private struct Bubble: Identifiable {
    let id = UUID()
    let text: String
    let outgoing: Bool
  }

  private var firstName: String {
    let given = AuthService.shared.givenName.trimmingCharacters(in: .whitespaces)
    if !given.isEmpty { return given }
    let display = AuthService.shared.displayName.trimmingCharacters(in: .whitespaces)
    return display.isEmpty ? "there" : (display.components(separatedBy: " ").first ?? display)
  }

  private var bubbles: [Bubble] {
    [
      Bubble(text: "Hey \(firstName) — how's omi feeling so far?", outgoing: false),
      Bubble(text: "honestly great. the drafts are landing better than I expected", outgoing: true),
      Bubble(
        text: "Love that. Ping us right here anytime — we usually reply fast.",
        outgoing: false),
    ]
  }

  var body: some View {
    ScrollView {
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
            Text("We usually reply fast.").inkSmall()
          }
        }

        // Chat bubbles.
        VStack(spacing: 10) {
          ForEach(bubbles) { b in
            HStack {
              if b.outgoing { Spacer(minLength: 40) }
              bubbleView(b)
              if !b.outgoing { Spacer(minLength: 40) }
            }
          }
        }
        .padding(.top, InkSpace.s5)

        // Message input (static).
        HStack(spacing: 10) {
          Image(systemName: "paperplane")
            .font(.system(size: 15))
            .foregroundColor(Ink.faint)
          Text("Message the team…")
            .font(InkFont.sans(14))
            .foregroundColor(Ink.faint)
          Spacer()
        }
        .padding(.horizontal, 16)
        .frame(height: 48)
        .background(
          RoundedRectangle(cornerRadius: 11, style: .continuous)
            .fill(Ink.surface)
            .overlay(
              RoundedRectangle(cornerRadius: 11, style: .continuous)
                .strokeBorder(Ink.hair2, lineWidth: 1))
        )
        .padding(.top, InkSpace.s5)

        // Links to the real destinations.
        HStack(spacing: 12) {
          InkButton(title: "Join Discord", kind: .plain) { open(Self.discordURL) }
          InkButton(title: "Read the docs", kind: .ghost) { open(Self.docsURL) }
          InkButton(title: "Source code ↗", kind: .ghost) { open(Self.sourceURL) }
        }
        .padding(.top, InkSpace.s5)
      }
      .frame(maxWidth: 640, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.horizontal, 48)
      .padding(.vertical, 44)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
  }

  @ViewBuilder
  private func bubbleView(_ b: Bubble) -> some View {
    let shape = UnevenRoundedRectangle(
      topLeadingRadius: 16,
      bottomLeadingRadius: b.outgoing ? 16 : 5,
      bottomTrailingRadius: b.outgoing ? 5 : 16,
      topTrailingRadius: 16,
      style: .continuous)
    Text(b.text)
      .font(InkFont.sans(13.5))
      .foregroundColor(b.outgoing ? Ink.accentInk : Ink.ink)
      .lineSpacing(2)
      .padding(.horizontal, 13)
      .padding(.vertical, 9)
      .background(
        shape
          .fill(b.outgoing ? Ink.ink : Ink.surface2)
          .overlay(shape.strokeBorder(b.outgoing ? Color.clear : Ink.hair, lineWidth: 1))
      )
      .frame(maxWidth: 420, alignment: b.outgoing ? .trailing : .leading)
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
