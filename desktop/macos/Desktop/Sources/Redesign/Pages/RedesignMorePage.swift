import SwiftUI

/// "All features" launcher grid — mockup `more.html`. The calm home stays out of
/// the way; everything the app can do lives here, one tap away.
struct RedesignMorePage: View {
  @Binding var selectedIndex: Int

  private struct Feature: Identifiable {
    let id = UUID()
    let icon: String
    let title: String
    let sub: String
    let index: Int
  }

  private let features: [Feature] = [
    .init(icon: "house", title: "Home", sub: "Your one next move", index: 0),
    .init(icon: "sparkles", title: "Ask omi", sub: "Anything you've seen or said", index: 2),
    .init(icon: "waveform", title: "Conversations", sub: "Every talk, summarized", index: 1),
    .init(icon: "message", title: "Messages", sub: "Drafts & auto-reply", index: 23),
    .init(icon: "brain", title: "Memory", sub: "Facts & everything kept", index: 3),
    .init(icon: "point.3.connected.trianglepath.dotted", title: "Brain map", sub: "How it all connects", index: 24),
    .init(icon: "checklist", title: "Tasks", sub: "What you owe, by when", index: 4),
    .init(icon: "eye", title: "Focus", sub: "Protect your best hours", index: 5),
    .init(icon: "lightbulb", title: "Insights", sub: "Quiet things I noticed", index: 6),
    .init(icon: "clock.arrow.circlepath", title: "Rewind", sub: "Find anything you saw", index: 7),
    .init(icon: "puzzlepiece", title: "Apps", sub: "Connect & export", index: 8),
    .init(icon: "theatermasks", title: "Persona", sub: "How I sound as you", index: 21),
    .init(icon: "gearshape", title: "Settings", sub: "Everything, tuned", index: 9),
    .init(icon: "bubble.left", title: "Talk to a founder", sub: "We usually reply fast", index: 12),
  ]

  private let columns = [GridItem(.adaptive(minimum: 220), spacing: 16)]

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 6) {
        Text("Everything, one tap away").inkMonoCaption()
        Text("All of omi").inkH1()
        Text("The calm home stays out of your way. Everything lives here.")
          .inkSmall().padding(.bottom, 12)

        LazyVGrid(columns: columns, spacing: 16) {
          ForEach(features) { f in
            Button { selectedIndex = f.index } label: { card(f) }
              .buttonStyle(.plain)
          }
        }
      }
      .frame(maxWidth: 900, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.horizontal, 48)
      .padding(.vertical, 44)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
  }

  private func card(_ f: Feature) -> some View {
    InkCard(padding: 18) {
      VStack(alignment: .leading, spacing: 10) {
        ZStack {
          RoundedRectangle(cornerRadius: 9, style: .continuous).fill(Ink.surface2)
            .frame(width: 34, height: 34)
          Image(systemName: f.icon).font(.system(size: 15)).foregroundColor(Ink.ink)
        }
        Text(f.title).inkH3()
        Text(f.sub).inkCaption()
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    }
  }
}
