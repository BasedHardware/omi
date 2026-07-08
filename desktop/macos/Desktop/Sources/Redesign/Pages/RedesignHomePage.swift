import SwiftUI

/// The home hub — greeting, the ask bar, the live transcript, and a grid of
/// feature cards that replaces the old nav rail. All live-wired.
struct RedesignHomePage: View {
  @ObservedObject var appState: AppState
  @Binding var selectedIndex: Int

  private struct Feature: Identifiable {
    let id = UUID()
    let icon: String
    let title: String
    let sub: String
    let index: Int
  }

  private let features: [Feature] = [
    .init(icon: "sparkles", title: "Ask omi", sub: "Anything you've seen or said", index: 2),
    .init(icon: "waveform", title: "Conversations", sub: "Every talk, summarized", index: 1),
    .init(icon: "brain", title: "Memory", sub: "Facts & everything kept", index: 3),
    .init(icon: "message", title: "Messages", sub: "Drafts & auto-reply", index: 23),
    .init(icon: "checklist", title: "Tasks", sub: "What you owe, by when", index: 4),
    .init(icon: "clock.arrow.circlepath", title: "Rewind", sub: "Find anything you saw", index: 7),
    .init(icon: "puzzlepiece", title: "Apps", sub: "Connect & export", index: 8),
    .init(icon: "point.3.connected.trianglepath.dotted", title: "Brain map", sub: "How it all connects", index: 24),
    .init(icon: "eye", title: "Focus", sub: "Protect your best hours", index: 5),
    .init(icon: "lightbulb", title: "Insights", sub: "Quiet things I noticed", index: 6),
    .init(icon: "theatermasks", title: "Persona", sub: "How I sound as you", index: 21),
    .init(icon: "gearshape", title: "Settings", sub: "Everything, tuned", index: 9),
  ]

  private let columns = [GridItem(.adaptive(minimum: 210), spacing: 14)]

  private var name: String {
    let given = AuthService.shared.givenName.trimmingCharacters(in: .whitespaces)
    if !given.isEmpty { return given }
    let display = AuthService.shared.displayName.trimmingCharacters(in: .whitespaces)
    return display.isEmpty ? "there" : display.components(separatedBy: " ").first ?? display
  }

  private var greeting: String {
    let hour = Calendar.current.component(.hour, from: Date())
    switch hour {
    case 5..<12: return "Good morning"
    case 12..<17: return "Good afternoon"
    case 17..<22: return "Good evening"
    default: return "Still up"
    }
  }

  private var dateLine: String {
    let f = DateFormatter()
    f.dateFormat = "EEEE, MMMM d"
    return f.string(from: Date())
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 24) {
        header
        askBar
        HomeLiveTranscript(isActive: appState.isTranscribing)
        cardGrid
        footer
      }
      .frame(maxWidth: 840, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.horizontal, 48)
      .padding(.vertical, 44)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
  }

  private var header: some View {
    HStack(alignment: .top) {
      VStack(alignment: .leading, spacing: 8) {
        Text(dateLine).inkMonoCaption()
        Text("\(greeting), \(name).").inkH1()
      }
      Spacer()
      Button {
        if let url = URL(string: "https://affiliate.omi.me") { NSWorkspace.shared.open(url) }
      } label: { MemberBadge(text: "Member") }
      .buttonStyle(.plain)
    }
  }

  private var askBar: some View {
    Button {
      FloatingControlBarManager.shared.openAIInput()
    } label: {
      HStack(spacing: 12) {
        Image(systemName: "sparkles").font(.system(size: 15)).foregroundColor(Ink.faint)
        Text("Ask omi anything — it remembers what you saw and said")
          .font(InkFont.sans(14)).foregroundColor(Ink.faint)
        Spacer()
        Text("⌘K").font(InkFont.mono(11)).foregroundColor(Ink.faint)
          .padding(.horizontal, 6).padding(.vertical, 2)
          .background(RoundedRectangle(cornerRadius: 5).fill(Ink.surface2)
            .overlay(RoundedRectangle(cornerRadius: 5).strokeBorder(Ink.hair, lineWidth: 1)))
      }
      .padding(.horizontal, 18)
      .frame(height: 52)
      .background(
        Capsule().fill(Ink.surface).overlay(Capsule().strokeBorder(Ink.hair2, lineWidth: 1)))
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
  }

  private var cardGrid: some View {
    LazyVGrid(columns: columns, spacing: 14) {
      ForEach(features) { f in
        Button { selectedIndex = f.index } label: { card(f) }
          .buttonStyle(.plain)
      }
    }
    .padding(.top, 4)
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

  private var footer: some View {
    HStack(spacing: 6) {
      Image(systemName: "lock").font(.system(size: 11)).foregroundColor(Ink.faint)
      Text("On your Mac · encrypted · you own it all.").inkCaption()
    }
    .padding(.top, 8)
  }
}

/// Live transcript card — Ink-styled, wired to the real `LiveTranscriptMonitor`.
///
/// Observes the shared monitor internally so streaming segment updates re-render
/// only this card, not the whole Home page. When transcription is active it
/// streams the user's actual live segments (speaker + text, auto-scrolling,
/// exactly the same data the app's `LiveTranscriptPanel`/`LiveTranscriptView`
/// render). When idle it shows the calm resting state.
private struct HomeLiveTranscript: View {
  @ObservedObject private var monitor = LiveTranscriptMonitor.shared
  let isActive: Bool

  /// Real live segments; falls back to the last snapshot after recording stops.
  private var segments: [SpeakerSegment] {
    if !monitor.segments.isEmpty { return monitor.segments }
    return monitor.savedSegments
  }

  /// Lightweight fingerprint that changes on any content growth (drives autoscroll).
  private var scrollTrigger: String {
    guard let last = segments.last else { return "" }
    return "\(segments.count)-\(last.id)-\(last.text.count)"
  }

  var body: some View {
    InkCard {
      VStack(alignment: .leading, spacing: 16) {
        header
        content
      }
      .frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  private var header: some View {
    HStack(spacing: 7) {
      if isActive {
        LiveDot(size: 6)
        Text("LIVE TRANSCRIPT")
          .font(InkFont.sans(11, .semibold)).foregroundColor(Ink.sentText).tracking(1.2)
      } else {
        Circle().fill(Ink.faint.opacity(0.5)).frame(width: 6, height: 6)
        Text("LIVE TRANSCRIPT")
          .font(InkFont.sans(11, .semibold)).foregroundColor(Ink.faint).tracking(1.2)
      }
      Spacer()
      if isActive {
        Text(segments.isEmpty ? "Listening" : "Listening · live").inkCaption()
      }
    }
  }

  @ViewBuilder private var content: some View {
    if isActive && !segments.isEmpty {
      transcriptScroll
    } else if isActive {
      restingRow(icon: "waveform", text: "Listening — start talking and I'll transcribe it here.")
    } else {
      restingRow(icon: "ear", text: "I'm listening when you are.")
    }
  }

  private func restingRow(icon: String, text: String) -> some View {
    HStack(spacing: 12) {
      Image(systemName: icon).font(.system(size: 18)).foregroundColor(Ink.faint)
      Text(text).inkSmall().fixedSize(horizontal: false, vertical: true)
      Spacer(minLength: 0)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.vertical, 6)
  }

  private var transcriptScroll: some View {
    ScrollViewReader { proxy in
      ScrollView {
        VStack(alignment: .leading, spacing: 14) {
          ForEach(segments) { segment in
            segmentRow(segment)
          }
          // Stable bottom anchor for autoscroll.
          Color.clear.frame(height: 1).id("home-transcript-bottom")
        }
        .padding(.vertical, 2)
        .frame(maxWidth: .infinity, alignment: .leading)
      }
      .frame(height: 220)
      .defaultScrollAnchor(.bottom)
      .onChange(of: scrollTrigger) { _, _ in
        withAnimation(.easeOut(duration: 0.2)) {
          proxy.scrollTo("home-transcript-bottom", anchor: .bottom)
        }
      }
    }
  }

  private func segmentRow(_ segment: SpeakerSegment) -> some View {
    let label = segment.isUser ? "You" : "Speaker \(segment.speaker)"
    return VStack(alignment: .leading, spacing: 4) {
      HStack(spacing: 7) {
        Circle()
          .fill(segment.isUser ? Ink.ink : Ink.avatarFill(for: label))
          .frame(width: 6, height: 6)
        Text(label)
          .font(InkFont.sans(11, .semibold))
          .foregroundColor(segment.isUser ? Ink.ink : Ink.muted)
          .tracking(0.3)
      }
      Text(segment.text)
        .font(InkFont.serif(15))
        .foregroundColor(Ink.body)
        .textSelection(.enabled)
        .fixedSize(horizontal: false, vertical: true)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}
