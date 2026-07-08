import SwiftUI

// MARK: - Guided app tour (coach-marks)
//
// A self-contained SwiftUI overlay that runs right after onboarding. It walks the
// user through the real app: as each step appears it navigates to the relevant page
// (via `selectedIndex`) so the live screen shows behind a small coach-mark card, and
// the card points toward the matching rail item (approximate anchor near the 68px
// left rail). A couple of "do it now" beats let the user try omi in flow.
//
// Present it as an overlay on the main window, gated by an @AppStorage flag:
//
//   .overlay {
//     if !hasSeenAppTour {
//       RedesignAppTour(selectedIndex: $selectedIndex) { hasSeenAppTour = true }
//     }
//   }
//
// where `@AppStorage("hasSeenAppTour") private var hasSeenAppTour = false`.
// `onFinish()` fires on both "finish" and "skip".

// MARK: - Model

/// Where the coach-mark card sits and which way its little pointer nub faces.
enum TourPointer: Equatable {
  /// Points left at a rail item. `y` is roughly the item's center from the window top.
  case rail(y: CGFloat)
  /// Points left at a rail item near the bottom. `y` is measured from the window bottom.
  case railBottom(y: CGFloat)
  /// Points up at the Capture / Listening chips in the top-right presence bar.
  case topRight
  /// Centered card, no pointer (welcome / farewell).
  case center
}

/// An optional "do it now" side effect fired when the user taps the primary button.
enum TourAction {
  /// Opens the floating ask bar so the user can try asking omi something.
  case openAsk
}

/// One coach-mark step. Edit this list (`RedesignAppTour.steps`) to reshape the tour.
struct TourStep: Identifiable {
  let id = UUID()
  /// Page to navigate to as the step appears (raw `selectedIndex`). `nil` keeps the current page.
  var route: Int?
  var title: String
  /// One short, warm, omi-voice line.
  var body: String
  var pointer: TourPointer
  /// Label for the advance button. Defaults to "Next" / "Done" on the last step.
  var primaryLabel: String? = nil
  var action: TourAction? = nil
}

// MARK: - Overlay

struct RedesignAppTour: View {
  @Binding var selectedIndex: Int
  let onFinish: () -> Void

  @State private var index: Int = 0

  // Approximate rail-item center Y positions (68px rail, items stacked from the top).
  // Home 0, Ask/Chat 2, Conversations 1, Memory 3, Messages 23, Tasks 4, Rewind 7.
  private static let steps: [TourStep] = [
    TourStep(
      route: 0,
      title: "Hi, I'm omi",
      body: "Give me two minutes and I'll show you around. Then you're all set.",
      pointer: .center,
      primaryLabel: "Show me"),
    TourStep(
      route: 0,
      title: "Home",
      body: "Your one next move lives here. I'll always tell you the single thing to do next.",
      pointer: .rail(y: 92)),
    TourStep(
      route: 2,
      title: "Ask omi",
      body: "Ask me anything — about your day, your notes, or the people in your life.",
      pointer: .rail(y: 136)),
    TourStep(
      route: 2,
      title: "Go on, try it",
      body: "I'll pop open the ask bar. Type a question, like \"what did I say I'd do today?\"",
      pointer: .center,
      primaryLabel: "Open ask bar",
      action: .openAsk),
    TourStep(
      route: 1,
      title: "Conversations",
      body: "Everything you talk about, transcribed and summarized. Nothing slips away.",
      pointer: .rail(y: 180)),
    TourStep(
      route: 3,
      title: "Memory",
      body: "The facts I remember about you and your world. This is your brain, saved.",
      pointer: .rail(y: 224)),
    TourStep(
      route: 23,
      title: "Messages",
      body: "I draft replies in your own voice, so answering people takes just one tap.",
      pointer: .rail(y: 268)),
    TourStep(
      route: 4,
      title: "Tasks",
      body: "Every to-do I hear becomes a task here. Check them off as you go.",
      pointer: .rail(y: 312)),
    TourStep(
      route: 7,
      title: "Rewind",
      body: "Scroll back through your screen and audio to find any moment you missed.",
      pointer: .rail(y: 356)),
    TourStep(
      route: 8,
      title: "Apps",
      body: "Plug omi into the tools you already use, so it fits right into your day.",
      pointer: .railBottom(y: 92)),
    TourStep(
      route: 9,
      title: "Settings",
      body: "Tune omi to fit you — capture, shortcuts, and everything in between.",
      pointer: .railBottom(y: 40)),
    TourStep(
      route: 0,
      title: "Turn on Capture & Listening",
      body: "Flip these on up here so I can start seeing and hearing for you.",
      pointer: .topRight),
    TourStep(
      route: 0,
      title: "You're all set",
      body: "That's the whole tour. I'll take it from here — talk to you soon.",
      pointer: .center,
      primaryLabel: "Start using omi"),
  ]

  private var step: TourStep { Self.steps[index] }
  private var isLast: Bool { index == Self.steps.count - 1 }
  private var isFirst: Bool { index == 0 }

  var body: some View {
    GeometryReader { geo in
      ZStack {
        // Soft scrim: dim enough to focus the card, light enough to keep the real
        // screen readable behind it. Swallows stray clicks so the tour stays put.
        Color.black.opacity(0.22)
          .ignoresSafeArea()
          .contentShape(Rectangle())
          .onTapGesture {}

        coachMark
          .frame(width: 330, alignment: .leading)
          .position(cardPosition(in: geo.size))
          .id(index)  // re-trigger the transition on each step
          .transition(
            .asymmetric(
              insertion: .opacity.combined(with: .offset(y: 8)),
              removal: .opacity)
          )
      }
    }
    .onAppear { applyRoute() }
    .onChange(of: index) { _, _ in applyRoute() }
  }

  // MARK: Coach-mark card

  private var coachMark: some View {
    Group {
      switch step.pointer {
      case .rail, .railBottom:
        HStack(spacing: 0) {
          TourNub(direction: .leading)
          card
        }
      case .topRight:
        VStack(spacing: 0) {
          TourNub(direction: .top)
          card
        }
      case .center:
        card
      }
    }
    .animation(.easeOut(duration: 0.22), value: index)
  }

  private var card: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Header: progress dots + skip
      HStack(alignment: .center) {
        progressDots
        Spacer(minLength: 12)
        Button(action: finish) {
          Text("Skip tour")
            .font(InkFont.sans(12, .medium))
            .foregroundColor(Ink.faint)
        }
        .buttonStyle(.plain)
      }
      .padding(.bottom, 14)

      Text(step.title)
        .inkH3()
      Text(step.body)
        .font(InkFont.sans(13.5, .regular))
        .foregroundColor(Ink.body)
        .lineSpacing(2)
        .fixedSize(horizontal: false, vertical: true)
        .padding(.top, 6)

      HStack(spacing: 10) {
        if !isFirst {
          InkButton(title: "Back", kind: .ghost, size: .sm) { back() }
        }
        Spacer(minLength: 0)
        Text("\(index + 1) of \(Self.steps.count)")
          .font(InkFont.sans(11.5, .medium))
          .foregroundColor(Ink.faint)
        InkButton(title: primaryTitle, kind: .primary, size: .sm) { advance() }
      }
      .padding(.top, 20)
    }
    .padding(20)
    .background(
      RoundedRectangle(cornerRadius: InkRadius.card, style: .continuous)
        .fill(Ink.surface)
        .overlay(
          RoundedRectangle(cornerRadius: InkRadius.card, style: .continuous)
            .strokeBorder(Ink.hair, lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.14), radius: 22, x: 0, y: 12)
    )
    .frame(width: 320)
  }

  private var progressDots: some View {
    HStack(spacing: 5) {
      ForEach(Self.steps.indices, id: \.self) { i in
        Capsule()
          .fill(i == index ? Ink.ink : Ink.hair2)
          .frame(width: i == index ? 16 : 6, height: 6)
          .animation(.easeOut(duration: 0.2), value: index)
      }
    }
  }

  private var primaryTitle: String {
    if let label = step.primaryLabel { return label }
    return isLast ? "Done" : "Next"
  }

  // MARK: Positioning

  private func cardPosition(in size: CGSize) -> CGPoint {
    let groupWidth: CGFloat = 330  // nub + card
    let railInset: CGFloat = 80  // just right of the 68px rail
    switch step.pointer {
    case .rail(let y):
      let cy = min(max(y, 130), size.height - 130)
      return CGPoint(x: railInset + groupWidth / 2, y: cy)
    case .railBottom(let y):
      let cy = min(max(size.height - y, 130), size.height - 130)
      return CGPoint(x: railInset + groupWidth / 2, y: cy)
    case .topRight:
      return CGPoint(x: size.width - 190, y: 96)
    case .center:
      return CGPoint(x: size.width / 2, y: size.height / 2)
    }
  }

  // MARK: Actions

  private func applyRoute() {
    if let route = step.route, route != selectedIndex {
      withAnimation(.easeOut(duration: 0.12)) { selectedIndex = route }
    }
  }

  private func advance() {
    if let action = step.action { perform(action) }
    if isLast {
      finish()
    } else {
      withAnimation(.easeOut(duration: 0.22)) { index += 1 }
    }
  }

  private func back() {
    guard !isFirst else { return }
    withAnimation(.easeOut(duration: 0.22)) { index -= 1 }
  }

  private func perform(_ action: TourAction) {
    switch action {
    case .openAsk:
      FloatingControlBarManager.shared.openAIInput()
    }
  }

  private func finish() {
    onFinish()
  }
}

// MARK: - Pointer nub

/// A small solid triangle nub that visually tethers the card to its target.
private struct TourNub: View {
  enum Direction { case leading, top }
  let direction: Direction

  var body: some View {
    TourTriangle(direction: direction)
      .fill(Ink.surface)
      .overlay(TourTriangle(direction: direction).stroke(Ink.hair, lineWidth: 1))
      .frame(
        width: direction == .leading ? 10 : 18,
        height: direction == .leading ? 18 : 10)
  }
}

private struct TourTriangle: Shape {
  let direction: TourNub.Direction
  func path(in rect: CGRect) -> Path {
    var p = Path()
    switch direction {
    case .leading:  // tip points left
      p.move(to: CGPoint(x: rect.minX, y: rect.midY))
      p.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
      p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
    case .top:  // tip points up
      p.move(to: CGPoint(x: rect.midX, y: rect.minY))
      p.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
      p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
    }
    p.closeSubpath()
    return p
  }
}
