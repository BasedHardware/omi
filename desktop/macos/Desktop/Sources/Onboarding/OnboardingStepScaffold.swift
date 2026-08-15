import AppKit
import OmiTheme
import SwiftUI

/// Back action for the current onboarding step, injected by `OnboardingView`.
/// `nil` on the first step (nothing to return to), which hides the back button.
private struct OnboardingBackActionKey: EnvironmentKey {
  static let defaultValue: (@MainActor () -> Void)? = nil
}

extension EnvironmentValues {
  var onboardingBack: (@MainActor () -> Void)? {
    get { self[OnboardingBackActionKey.self] }
    set { self[OnboardingBackActionKey.self] = newValue }
  }
}

/// Jump straight to a step index, injected by `OnboardingView`. Powers the
/// clickable progress dots so the user can move to any step directly.
private struct OnboardingJumpActionKey: EnvironmentKey {
  static let defaultValue: (@MainActor (Int) -> Void)? = nil
}

extension EnvironmentValues {
  var onboardingJumpTo: (@MainActor (Int) -> Void)? {
    get { self[OnboardingJumpActionKey.self] }
    set { self[OnboardingJumpActionKey.self] = newValue }
  }
}

/// Highest step the user has cleared. Combined with `OnboardingFlow.canJump`,
/// this decides which progress dots are clickable: anything already cleared, plus
/// forward jumps that only pass over skippable steps.
private struct OnboardingFurthestStepKey: EnvironmentKey {
  static let defaultValue: Int = .max
}

extension EnvironmentValues {
  var onboardingFurthestStep: Int {
    get { self[OnboardingFurthestStepKey.self] }
    set { self[OnboardingFurthestStepKey.self] = newValue }
  }
}

enum OnboardingRightPaneMode {
  case graph
  case message(title: String, detail: String)
}

enum OnboardingLayoutMode {
  case split
  case centered
}

/// Keeps the onboarding chrome visible while allowing a step's content to
/// scroll only when a compact window cannot contain it. The minimum-height
/// frame preserves the existing centered composition at ordinary sizes.
struct OnboardingCenteredContentRegion<Content: View>: View {
  let content: Content

  init(@ViewBuilder content: () -> Content) {
    self.content = content()
  }

  var body: some View {
    GeometryReader { geometry in
      ScrollView(showsIndicators: false) {
        content
          .frame(maxWidth: .infinity)
          .frame(minHeight: geometry.size.height, alignment: .center)
          .padding(.horizontal, OmiSpacing.page)
          .padding(.vertical, OmiSpacing.section)
      }
      .scrollBounceBehavior(.basedOnSize)
    }
  }
}

/// Splits an onboarding step into scrollable content and persistent navigation
/// actions. Keeping the footer outside the scroll view ensures users can
/// always go back or continue, even while a compact-height window scrolls the
/// larger instructional content.
struct OnboardingContentWithPinnedActions<Content: View, Actions: View>: View {
  let content: Content
  let actions: Actions

  init(
    @ViewBuilder content: () -> Content,
    @ViewBuilder actions: () -> Actions
  ) {
    self.content = content()
    self.actions = actions()
  }

  var body: some View {
    VStack(spacing: 0) {
      OnboardingCenteredContentRegion { content }
        .frame(maxHeight: .infinity)

      actions
        .padding(.horizontal, OmiSpacing.page)
        .padding(.bottom, OmiSpacing.section)
    }
  }
}

struct OnboardingStepScaffold<Content: View>: View {
  @ObservedObject private var graphViewModel: MemoryGraphViewModel
  @Environment(\.onboardingJumpTo) private var onboardingJumpTo

  let stepIndex: Int
  let totalSteps: Int
  let eyebrow: String
  let title: String
  let description: String
  let layoutMode: OnboardingLayoutMode
  let rightPaneMode: OnboardingRightPaneMode
  let rightPaneFooterText: String?
  /// When true (split layout only), the graph/second-brain pane renders on the
  /// leading side and the step content on the trailing side — the mirror of the
  /// default. Used by the exports step.
  let graphLeading: Bool
  let showsSkip: Bool
  let onSkip: (() -> Void)?
  let onForceComplete: (() -> Void)?
  let content: Content

  init(
    graphViewModel: MemoryGraphViewModel,
    stepIndex: Int,
    totalSteps: Int,
    eyebrow: String,
    title: String,
    description: String,
    layoutMode: OnboardingLayoutMode = .split,
    rightPaneMode: OnboardingRightPaneMode = .graph,
    rightPaneFooterText: String? = nil,
    graphLeading: Bool = false,
    showsSkip: Bool = false,
    onSkip: (() -> Void)? = nil,
    onForceComplete: (() -> Void)? = nil,
    @ViewBuilder content: () -> Content
  ) {
    _graphViewModel = ObservedObject(wrappedValue: graphViewModel)
    self.stepIndex = stepIndex
    self.totalSteps = totalSteps
    self.eyebrow = eyebrow
    self.title = title
    self.description = description
    self.layoutMode = layoutMode
    self.rightPaneMode = rightPaneMode
    self.rightPaneFooterText = rightPaneFooterText
    self.graphLeading = graphLeading
    self.showsSkip = showsSkip
    self.onSkip = onSkip
    self.onForceComplete = onForceComplete
    self.content = content()
  }

  var body: some View {
    switch layoutMode {
    case .split:
      HStack(spacing: 0) {
        if graphLeading {
          OnboardingSecondBrainPane(
            graphViewModel: graphViewModel,
            mode: rightPaneMode,
            footerText: rightPaneFooterText
          )
          .frame(maxWidth: .infinity, maxHeight: .infinity)

          // Directional flow: memories (left) export to your tools (right).
          // The chip is overlaid on the divider so it sits dead-center on the
          // dividing line. Muted to blend in; shape matches the chat send button.
          // Fixed-width column so the chip isn't clipped by the neighboring pane;
          // the line runs full height and the chip sits centered on it.
          ZStack {
            Rectangle()
              .fill(Ink.separator)
              .frame(width: 1)
              .frame(maxHeight: .infinity)
              // The chip used to knock the rule out with an opaque disc of the page colour. On glass
              // there is no page colour to knock out *with* — the ground is the blurred desktop, so a
              // filled disc is a grey blob and no disc leaves the rule crossing the glyph. The rule is
              // **masked** where the chip sits instead, the same answer `glassScrollFade` gives for
              // the same reason. The band is the glyph plus its padding, and it carries the chip's own
              // offset so the two cannot drift apart.
              .mask {
                VStack(spacing: 0) {
                  Rectangle()
                  Color.clear.frame(height: 34)
                  Rectangle()
                }
                .offset(y: -64)
              }
            Image(systemName: "arrow.right.circle.fill")
              .scaledFont(size: 24)
              .foregroundColor(Ink.secondary)
              .padding(4)
              // Raised to sit at the vertical middle of the graph, which centers
              // higher than the full pane (the footer summary sits below it).
              .offset(y: -64)
          }
          .frame(width: 40)

          splitPane
            .frame(minWidth: 470, idealWidth: 520, maxWidth: 560)
        } else {
          splitPane
            .frame(minWidth: 470, idealWidth: 520, maxWidth: 560)

          Rectangle()
            .fill(Ink.separator)
            .frame(width: 1)
            .frame(maxHeight: .infinity)

          OnboardingSecondBrainPane(
            graphViewModel: graphViewModel,
            mode: rightPaneMode,
            footerText: rightPaneFooterText
          )
          .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)

    case .centered:
      VStack(spacing: 0) {
        header

        GlassSeparator()

        progressRow

        GeometryReader { geometry in
          ScrollView(showsIndicators: false) {
            VStack(spacing: OmiSpacing.xxl) {
              titleBlock(centered: true)
              content
            }
            // Optical centering: phantom bottom padding lifts the block a bit
            // above true vertical center.
            .padding(.bottom, 96)
            .frame(maxWidth: 560)
            .frame(
              minWidth: 0, maxWidth: .infinity, minHeight: geometry.size.height,
              maxHeight: .infinity, alignment: .center
            )
            .padding(.horizontal, OmiSpacing.page)
            .padding(.vertical, OmiSpacing.section)
          }
          // Only scroll when content genuinely overflows — no elastic bounce
          // on steps (e.g. the permission steps) whose content already fits.
          .scrollBounceBehavior(.basedOnSize)
        }
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
  }

  private var splitPane: some View {
    VStack(spacing: 0) {
      header

      GlassSeparator()

      progressRow

      ScrollView(showsIndicators: false) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
          titleBlock(centered: false)
          content
        }
        .frame(maxWidth: 500, alignment: .leading)
        .padding(.horizontal, OmiSpacing.page)
        .padding(.vertical, OmiSpacing.section)
      }
      // Only scroll when content genuinely overflows — no elastic bounce on
      // steps (e.g. the permission steps) whose content already fits.
      .scrollBounceBehavior(.basedOnSize)
    }
  }

  private var header: some View {
    HStack {
      OnboardingLogoMark(onForceComplete: onForceComplete)

      Spacer()

      if showsSkip, let onSkip {
        Button(action: onSkip) {
          Text("Skip")
            .font(.system(size: 13, weight: .medium))
            .foregroundColor(Ink.secondary)
        }
        .buttonStyle(.plain)
      }
    }
    .padding(.horizontal, OmiSpacing.xxl)
    .padding(.vertical, OmiSpacing.lg)
  }

  /// Fixed top strip under the header divider, matching the custom full-width
  /// steps (shortcut/demo views) that place the bar themselves.
  private var progressRow: some View {
    OnboardingProgressBar(stepIndex: stepIndex, totalSteps: totalSteps)
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.top, OmiSpacing.xl)
  }

  private func titleBlock(centered: Bool) -> some View {
    VStack(alignment: centered ? .center : .leading, spacing: OmiSpacing.md) {
      if !eyebrow.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        Text(eyebrow.uppercased())
          .font(.system(size: 12, weight: .semibold))
          .tracking(1.2)
          .foregroundColor(Ink.secondary)
      }

      Text(title)
        .inkStyle(InkType.stepHeadline, color: Ink.primary)
        .multilineTextAlignment(centered ? .center : .leading)
        .fixedSize(horizontal: false, vertical: true)

      if !description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        Text(description)
          .inkStyle(InkType.prose, color: Ink.secondary)
          .multilineTextAlignment(centered ? .center : .leading)
          .fixedSize(horizontal: false, vertical: true)
          .frame(maxWidth: 460, alignment: centered ? .center : .leading)
      }
    }
    .frame(maxWidth: .infinity, alignment: centered ? .center : .leading)
  }
}

struct OnboardingLogoMark: View {
  let onForceComplete: (() -> Void)?

  var body: some View {
    Group {
      if let logoImage = onboardingTextLogoImage() {
        Image(nsImage: logoImage)
          .resizable()
          .renderingMode(.template)
          .foregroundColor(Ink.primary)
          .scaledToFit()
          .frame(width: 52, height: 18)
      } else {
        Text("omi")
          .font(.system(size: 18, weight: .semibold))
          .foregroundColor(Ink.primary)
      }
    }
    .contentShape(Rectangle())
    .onLongPressGesture(minimumDuration: 1) {
      onForceComplete?()
    }
    .accessibilityLabel("omi")
  }
}

/// Segmented progress bar shown at the top of an onboarding step: one capsule
/// per phase (`OnboardingFlow.phases`), sized by its page count. The fill tip
/// stands at the end of the completed pages, and clicking any part puts the
/// tip there (via the injected `onboardingJumpTo` action, gated by
/// `OnboardingFlow.canJump`). Hovering a segment reveals tick marks at its
/// page boundaries. Used by `OnboardingStepScaffold` and by the custom
/// full-width steps (floating-bar shortcut/demo) that don't use the scaffold.
struct OnboardingProgressBar: View {
  let stepIndex: Int
  let totalSteps: Int
  @Environment(\.onboardingJumpTo) private var onboardingJumpTo
  @Environment(\.onboardingFurthestStep) private var furthestStep
  @State private var hoveredPhase: Int?
  @State private var settledStep: Int?

  private static let pageWidth: CGFloat = 14
  private static let barHeight: CGFloat = 5

  /// The step the previous page's bar instance last showed. Each page hosts
  /// its own bar, so cross-page fill animation is faked by first rendering the
  /// previous page's fill and animating to the real value on appear — forward
  /// navigation grows the fill, backward navigation shrinks it back.
  @MainActor private static var lastRenderedStep: Int?

  /// The page the fill has animated up to. Before the on-appear animation
  /// settles, the starting fill is clamped to one page away from the target:
  /// pages already behind you render complete instantly and only the slice of
  /// the page being entered (or left, going backward) animates — a jump across
  /// several pages never sweeps them all.
  private var filledUpTo: Int {
    if let settledStep { return settledStep }
    guard let last = Self.lastRenderedStep else { return stepIndex }
    return last <= stepIndex ? max(last, stepIndex - 1) : stepIndex + 1
  }

  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      ForEach(OnboardingFlow.phases.indices, id: \.self) { index in
        segment(index)
      }
    }
    .onAppear {
      // The fill capsule's .animation(value: filled) turns this into the
      // one-slice grow/drain transition.
      settledStep = stepIndex
      Self.lastRenderedStep = stepIndex
    }
  }

  private func segment(_ phaseIndex: Int) -> some View {
    let phase = OnboardingFlow.phases[phaseIndex]
    let pages = phase.steps.count
    let width = CGFloat(pages) * Self.pageWidth
    // A page counts as filled only once you've moved past it, so the fill
    // always stands at the start of the current page's slot — the first page
    // shows no fill at all.
    let filled = phase.steps.filter { $0 < filledUpTo }.count

    return ZStack(alignment: .leading) {
      Capsule()
        .fill(Ink.hairline)
        .frame(width: width, height: Self.barHeight)
      Capsule()
        .fill(Ink.primary)
        .frame(width: width * CGFloat(filled) / CGFloat(pages), height: Self.barHeight)
        .animation(
          InkReduceMotion.animation(.snappy(duration: InkMotion.stepTransition)), value: filled)
      HStack(spacing: 0) {
        ForEach(phase.steps, id: \.self) { step in
          pageSlice(step, phase: phase, showTicks: hoveredPhase == phaseIndex)
        }
      }
    }
    .frame(width: width)
    .onHover { inside in
      if inside {
        hoveredPhase = phaseIndex
      } else if hoveredPhase == phaseIndex {
        hoveredPhase = nil
      }
    }
    .help(phase.title)
  }

  @ViewBuilder
  private func pageSlice(_ step: Int, phase: OnboardingFlow.Phase, showTicks: Bool) -> some View {
    let localIndex = step - phase.steps.lowerBound
    // The fill tip reads as "where you are", standing at the end of the
    // completed parts. Clicking any part — in any segment, forward or back —
    // means "put the tip at the end of this part": navigate to the page after
    // it (rolling into the next segment from a segment's last part).
    let target = min(step + 1, OnboardingFlow.lastStepIndex)
    // Pad the hit area vertically so the thin bar is comfortably clickable
    // without changing the row's visual layout.
    let slice = Color.clear
      .frame(width: Self.pageWidth, height: Self.barHeight)
      .padding(.vertical, OmiSpacing.sm)
      .contentShape(Rectangle())
      .overlay(alignment: .leading) {
        // Page-boundary tick, revealed on hover. Cut in the sheet colour so it
        // reads as the same notch over the filled and unfilled parts alike.
        if showTicks, localIndex > 0 {
          RoundedRectangle(cornerRadius: 0.75)
            .fill(Ink.surface)
            .frame(width: 1.5, height: Self.barHeight + 4)
            .offset(x: -0.75)
        }
      }

    // Clickable when the jump policy allows it: cleared steps always, forward
    // jumps only over skippable steps (see OnboardingFlow.canJump).
    if let onboardingJumpTo, OnboardingFlow.canJump(to: target, furthestStep: furthestStep) {
      Button {
        onboardingJumpTo(target)
      } label: {
        slice
      }
      .buttonStyle(.plain)
      .onHover { inside in
        if inside { NSCursor.pointingHand.push() } else { NSCursor.pop() }
      }
      .help("\(phase.title) — step \(localIndex + 1) of \(phase.steps.count)")
    } else {
      slice
    }
  }
}

/// A keycap styled like a physical Mac keyboard key: the symbol with the key's
/// name written under it (⌘ over "command"), and a wide cap for Return/Space.
/// Plain letter keys show just the letter. Used by the shortcut-setup steps.
struct OnboardingKeyCapView: View {
  let token: String
  var isActive: Bool = false

  private static let keyNames: [String: String] = [
    "⌘": "command", "⇧": "shift", "⌥": "option", "⌃": "control",
    "⇪": "caps lock", "↩": "return", "⏎": "return", "␣": "space",
    "Space": "space", "⎋": "esc", "⇥": "tab", "Right ⌘": "command",
  ]
  private static let wideTokens: Set<String> = ["↩", "⏎", "␣", "Space"]

  private var keyName: String? { Self.keyNames[token] }
  private var isWide: Bool { Self.wideTokens.contains(token) }

  var body: some View {
    // The label is part of layout (not an overlay) so the cap widens to keep
    // the key's name on a single line instead of wrapping ("comman/d").
    Group {
      if let keyName {
        // Named keys mirror a physical Mac key: symbol in the top-left
        // corner, name on one line along the bottom.
        VStack(spacing: 0) {
          Text(token)
            .font(.system(size: 18, weight: .semibold))
            .frame(maxWidth: .infinity, alignment: .leading)
          Spacer(minLength: 4)
          // Wide keys (return/space) carry their name in the bottom-right
          // corner like a physical keyboard; square keys center it.
          Text(keyName)
            .font(.system(size: 10, weight: .medium))
            .lineLimit(1)
            .fixedSize()
            .frame(maxWidth: .infinity, alignment: isWide ? .trailing : .center)
        }
      } else {
        // Plain letter keys show just the letter, centered.
        Text(token)
          .font(.system(size: 22, weight: .semibold))
      }
    }
    // The active cap inverts the label ladder, the way the primary button does:
    // `Ink.primary` fill, `Ink.surface` label.
    .foregroundColor(isActive ? Ink.surface : Ink.primary)
    .padding(.horizontal, 10)
    .padding(.vertical, 8)
    .frame(minWidth: isWide ? 116 : 64, minHeight: 64)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
        .fill(isActive ? Ink.primary : Ink.rowFill)
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
            .stroke(
              isActive ? Ink.primary : Ink.hairline,
              lineWidth: 2
            )
        )
    )
    .fixedSize()
  }
}

/// Grey "Back" button that returns to the previous onboarding step. Renders
/// nothing on the first step (where the injected `onboardingBack` action is nil).
/// Place it to the left of a step's Continue button.
struct OnboardingBackButton: View {
  @Environment(\.onboardingBack) private var onboardingBack

  var body: some View {
    if let onboardingBack {
      Button("Back", action: onboardingBack)
        .buttonStyle(InkButtonStyle(kind: .secondary))
        .accessibilityLabel("Back")
    }
  }
}

private struct OnboardingSecondBrainPane: View {
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let mode: OnboardingRightPaneMode
  let footerText: String?

  var body: some View {
    ZStack(alignment: .bottom) {
      // A wash, not a fill: the pane reads as a shade of the glass rather than
      // as a second background pasted over it.
      Ink.rowFill
        .ignoresSafeArea()

      VStack(spacing: 0) {
        graphBody

        if case .graph = mode, let footerText, !footerText.isEmpty {
          GlassSeparator()

          VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            Text("Who you are")
              .font(.system(size: 12, weight: .semibold))
              .foregroundColor(Ink.secondary)
              .tracking(0.6)

            Text(footerText)
              .font(.system(size: 13))
              .foregroundColor(Ink.secondary)
              .lineSpacing(3)
              .lineLimit(4)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(.horizontal, OmiSpacing.xxl)
          .padding(.vertical, OmiSpacing.lg)
        }
      }
    }
    .overlay(alignment: .top) {
      if case .graph = mode, !graphViewModel.isEmpty {
        OnboardingGraphBrandMark()
          .padding(.top, OmiSpacing.lg)
      }
    }
    .task {
      await graphViewModel.addGraphFromStorage()
      if graphViewModel.isEmpty {
        await graphViewModel.loadGraph()
      }
    }
  }

  @ViewBuilder
  private var graphBody: some View {
    switch mode {
    case .message(let title, let detail):
      VStack(spacing: OmiSpacing.md) {
        Text(title)
          .inkStyle(InkType.stepHeadline, color: Ink.primary)
          .multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)

        Text(detail)
          .inkStyle(InkType.prose, color: Ink.secondary)
          .multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)
          .frame(maxWidth: 320)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)

    case .graph:
      if graphViewModel.isEmpty {
        VStack(spacing: OmiSpacing.md) {
          Text("Your graph appears once Omi has something real to map.")
            .inkStyle(InkType.prose, color: Ink.secondary)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: 320)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        ZStack(alignment: .bottom) {
          MemoryGraphSceneView(viewModel: graphViewModel)
            .ignoresSafeArea()

          VStack(spacing: OmiSpacing.sm) {
            Text("This is your 2nd brain")
              .inkStyle(InkType.rowCopy, color: Ink.primary)
              .padding(.horizontal, OmiSpacing.md)
              .padding(.vertical, OmiSpacing.xs)

            HStack(spacing: OmiSpacing.xl) {
              graphHintItem(icon: "arrow.triangle.2.circlepath", label: "Drag to rotate")
              graphHintItem(icon: "magnifyingglass", label: "Scroll to zoom")
              graphHintItem(icon: "hand.draw", label: "Two-finger to pan")
            }
          }
          .padding(.horizontal, OmiSpacing.lg)
          .padding(.bottom, OmiSpacing.sm)
        }
      }
    }
  }

  private func graphHintItem(icon: String, label: String) -> some View {
    HStack(spacing: OmiSpacing.xxs) {
      Image(systemName: icon)
        .font(.system(size: 11))
      Text(label)
        .font(.system(size: 11))
    }
    .foregroundColor(Ink.secondary)
  }
}

private struct OnboardingGraphBrandMark: View {
  var body: some View {
    HStack(alignment: .firstTextBaseline, spacing: 0) {
      if let logoImage = onboardingTextLogoImage() {
        Image(nsImage: logoImage)
          .resizable()
          .renderingMode(.template)
          .foregroundColor(Ink.primary)
          .scaledToFit()
          .frame(width: 45, height: 20)
      } else {
        Text("omi")
          .font(.system(size: 20, weight: .semibold))
          .foregroundColor(Ink.primary)
      }

      Text(".me")
        .font(.system(size: 20, weight: .semibold))
        .foregroundColor(Ink.primary)
        .offset(y: -1)
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.xs)
    .glassChip()
    .accessibilityLabel("omi.me")
  }
}

private func onboardingTextLogoImage() -> NSImage? {
  guard
    let logoURL = Bundle.resourceBundle.url(forResource: "omi_text_logo", withExtension: "png"),
    let loadedLogoImage = NSImage(contentsOf: logoURL)
  else {
    return nil
  }
  let logoImage = loadedLogoImage.copy() as? NSImage ?? loadedLogoImage
  logoImage.isTemplate = true
  return logoImage
}

struct OnboardingInsightCard: View {
  let icon: String
  let title: String
  let detail: String

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      ZStack {
        RoundedRectangle(cornerRadius: PageGlass.chipRadius, style: .continuous)
          .fill(Ink.rowFillHover)
          .frame(width: 42, height: 42)

        Image(systemName: icon)
          .font(.system(size: 16, weight: .semibold))
          .foregroundColor(Ink.secondary)
      }

      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        Text(title)
          .inkStyle(InkType.rowCopy, color: Ink.primary)

        Text(detail)
          .font(.system(size: 13))
          .foregroundColor(Ink.secondary)
          .lineSpacing(3)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer()
    }
    .padding(OmiSpacing.lg)
    .glassCard()
  }
}

struct OnboardingSelectableChip: View {
  let title: String
  var leading: AnyView? = nil
  let isSelected: Bool
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      HStack(spacing: 7) {
        if let leading { leading }
        Text(title)
          .font(.system(size: 14, weight: .semibold))
          .foregroundColor(isSelected ? Ink.primary : Ink.secondary)
      }
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.sm)
      .glassChip(isActive: isSelected)
    }
    .buttonStyle(.plain)
  }
}
