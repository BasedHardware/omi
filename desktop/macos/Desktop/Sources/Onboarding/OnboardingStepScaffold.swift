import AppKit
import SwiftUI
import OmiTheme

/// Back action for the current onboarding step, injected by `OnboardingView`.
/// `nil` on the first step (nothing to return to), which hides the back button.
private struct OnboardingBackActionKey: EnvironmentKey {
  static let defaultValue: (() -> Void)? = nil
}

extension EnvironmentValues {
  var onboardingBack: (() -> Void)? {
    get { self[OnboardingBackActionKey.self] }
    set { self[OnboardingBackActionKey.self] = newValue }
  }
}

/// Jump straight to a step index, injected by `OnboardingView`. Powers the
/// clickable progress dots so the user can move to any step directly.
private struct OnboardingJumpActionKey: EnvironmentKey {
  static let defaultValue: ((Int) -> Void)? = nil
}

extension EnvironmentValues {
  var onboardingJumpTo: ((Int) -> Void)? {
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
    self.showsSkip = showsSkip
    self.onSkip = onSkip
    self.onForceComplete = onForceComplete
    self.content = content()
  }

  var body: some View {
    switch layoutMode {
    case .split:
      HStack(spacing: 0) {
        splitPane
          .frame(minWidth: 470, idealWidth: 520, maxWidth: 560)

        Divider()
          .background(OmiColors.backgroundTertiary)

        OnboardingSecondBrainPane(
          graphViewModel: graphViewModel,
          mode: rightPaneMode,
          footerText: rightPaneFooterText
        )
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .background(OmiColors.backgroundPrimary)

    case .centered:
      VStack(spacing: 0) {
        header

        Divider()
          .background(OmiColors.backgroundTertiary)

        GeometryReader { geometry in
          ScrollView(showsIndicators: false) {
            VStack(spacing: OmiSpacing.xxl) {
              progressRow(centered: true)
              titleBlock(centered: true)
              content
            }
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
      .background(OmiColors.backgroundPrimary)
    }
  }

  private var splitPane: some View {
    VStack(spacing: 0) {
      header

      Divider()
        .background(OmiColors.backgroundTertiary)

      ScrollView(showsIndicators: false) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
          progressRow(centered: false)
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
    .background(OmiColors.backgroundPrimary)
  }

  private var header: some View {
    HStack {
      OnboardingLogoMark(onForceComplete: onForceComplete)

      Spacer()

      if showsSkip, let onSkip {
        Button(action: onSkip) {
          Text("Skip")
            .font(.system(size: 13, weight: .medium))
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
      }
    }
    .padding(.horizontal, OmiSpacing.xxl)
    .padding(.vertical, OmiSpacing.lg)
  }

  private func progressRow(centered: Bool) -> some View {
    OnboardingProgressDots(stepIndex: stepIndex, totalSteps: totalSteps)
      .frame(maxWidth: .infinity, alignment: centered ? .center : .leading)
  }

  private func titleBlock(centered: Bool) -> some View {
    VStack(alignment: centered ? .center : .leading, spacing: OmiSpacing.md) {
      if !eyebrow.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        Text(eyebrow.uppercased())
          .font(.system(size: 12, weight: .semibold))
          .tracking(1.2)
          .foregroundColor(OmiColors.textTertiary)
      }

      Text(title)
        .font(.system(size: 40, weight: .bold))
        .foregroundColor(OmiColors.textPrimary)
        .lineSpacing(2)
        .multilineTextAlignment(centered ? .center : .leading)

      if !description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        Text(description)
          .font(.system(size: 16))
          .foregroundColor(OmiColors.textSecondary)
          .lineSpacing(4)
          .multilineTextAlignment(centered ? .center : .leading)
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
          .foregroundColor(.white)
          .scaledToFit()
          .frame(width: 52, height: 18)
      } else {
        Text("omi")
          .font(.system(size: 18, weight: .semibold))
          .foregroundColor(.white)
      }
    }
    .contentShape(Rectangle())
    .onLongPressGesture(minimumDuration: 1) {
      onForceComplete?()
    }
    .accessibilityLabel("omi")
  }
}

/// Progress dots shown at the top of an onboarding step. Each dot is clickable
/// (via the injected `onboardingJumpTo` action) so the user can jump straight to
/// any step. Used by `OnboardingStepScaffold` and by the custom full-width steps
/// (floating-bar shortcut/demo) that don't use the scaffold.
struct OnboardingProgressDots: View {
  let stepIndex: Int
  let totalSteps: Int
  @Environment(\.onboardingJumpTo) private var onboardingJumpTo
  @Environment(\.onboardingFurthestStep) private var furthestStep

  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      ForEach(0..<totalSteps, id: \.self) { index in
        dot(index)
      }
    }
  }

  @ViewBuilder
  private func dot(_ index: Int) -> some View {
    let capsule = Capsule()
      .fill(index <= stepIndex ? Color.white : Color.white.opacity(0.1))
      .frame(width: index == stepIndex ? 28 : 8, height: 6)

    // Clickable when the jump policy allows it: cleared steps always, forward
    // jumps only over skippable steps (see OnboardingFlow.canJump).
    if let onboardingJumpTo, OnboardingFlow.canJump(to: index, furthestStep: furthestStep) {
      Button {
        onboardingJumpTo(index)
      } label: {
        // Pad the hit area vertically so the 6pt dot is comfortably clickable
        // without changing the row's visual layout.
        capsule
          .padding(.vertical, OmiSpacing.sm)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .onHover { inside in
        if inside { NSCursor.pointingHand.push() } else { NSCursor.pop() }
      }
      .help("Go to step \(index + 1)")
    } else {
      capsule
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
    RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
      .fill(isActive ? Color.white : OmiColors.backgroundTertiary)
      .frame(minWidth: isWide ? 116 : 64, minHeight: 64)
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
          .stroke(
            isActive ? Color.white : OmiColors.textTertiary.opacity(0.3),
            lineWidth: 2
          )
      )
      .overlay(alignment: .topLeading) {
        // Named keys mirror a physical Mac key: symbol in the top-left corner…
        if keyName != nil {
          Text(token)
            .font(.system(size: 18, weight: .semibold))
            .foregroundColor(isActive ? .black : OmiColors.textPrimary)
            .padding(.top, 8)
            .padding(.leading, 10)
        }
      }
      .overlay(alignment: .bottom) {
        // …with the key's name written along the bottom.
        if let keyName {
          Text(keyName)
            .font(.system(size: 10, weight: .medium))
            .foregroundColor(isActive ? .black : OmiColors.textPrimary)
            .padding(.bottom, 8)
            .padding(.horizontal, 8)
        }
      }
      .overlay {
        // Plain letter keys show just the letter, centered.
        if keyName == nil {
          Text(token)
            .font(.system(size: 22, weight: .semibold))
            .foregroundColor(isActive ? .black : OmiColors.textPrimary)
            .padding(.horizontal, 12)
        }
      }
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
        .buttonStyle(OmiButtonStyle(.secondary))
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
      OmiColors.backgroundSecondary
        .ignoresSafeArea()

      VStack(spacing: 0) {
        graphBody

        if case .graph = mode, let footerText, !footerText.isEmpty {
          Divider()
            .background(Color.white.opacity(0.08))

          VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            Text("Who you are")
              .font(.system(size: 12, weight: .semibold))
              .foregroundColor(OmiColors.textTertiary)
              .tracking(0.6)

            Text(footerText)
              .font(.system(size: 13))
              .foregroundColor(OmiColors.textSecondary)
              .lineSpacing(3)
              .lineLimit(4)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(.horizontal, OmiSpacing.xxl)
          .padding(.vertical, OmiSpacing.lg)
          .background(OmiColors.backgroundPrimary.opacity(0.92))
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
          .font(.system(size: 28, weight: .bold))
          .foregroundColor(OmiColors.textPrimary)
          .multilineTextAlignment(.center)

        Text(detail)
          .font(.system(size: 15))
          .foregroundColor(OmiColors.textTertiary)
          .multilineTextAlignment(.center)
          .frame(maxWidth: 320)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)

    case .graph:
      if graphViewModel.isEmpty {
        VStack(spacing: OmiSpacing.md) {
          Text("Your graph appears once Omi has something real to map.")
            .font(.system(size: 15, weight: .medium))
            .foregroundColor(OmiColors.textTertiary)
            .multilineTextAlignment(.center)
            .frame(maxWidth: 320)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        ZStack(alignment: .bottom) {
          MemoryGraphSceneView(viewModel: graphViewModel)
            .ignoresSafeArea()

          VStack(spacing: OmiSpacing.sm) {
            Text("This is your 2nd brain")
              .font(.system(size: 15, weight: .semibold))
              .foregroundColor(.white)
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
    .foregroundColor(.white.opacity(0.5))
  }
}

private struct OnboardingGraphBrandMark: View {
  var body: some View {
    HStack(alignment: .firstTextBaseline, spacing: 0) {
      if let logoImage = onboardingTextLogoImage() {
        Image(nsImage: logoImage)
          .resizable()
          .renderingMode(.template)
          .foregroundColor(.white)
          .scaledToFit()
          .frame(width: 45, height: 20)
      } else {
        Text("omi")
          .font(.system(size: 20, weight: .semibold))
          .foregroundColor(.white)
      }

      Text(".me")
        .font(.system(size: 20, weight: .semibold))
        .foregroundColor(.white)
        .offset(y: -1)
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.xs)
    .background(Color.black.opacity(0.28))
    .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous))
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
        RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
          .fill(OmiColors.backgroundQuaternary)
          .frame(width: 42, height: 42)

        Image(systemName: icon)
          .font(.system(size: 16, weight: .semibold))
          .foregroundColor(OmiColors.textSecondary)
      }

      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        Text(title)
          .font(.system(size: 15, weight: .semibold))
          .foregroundColor(OmiColors.textPrimary)

        Text(detail)
          .font(.system(size: 13))
          .foregroundColor(OmiColors.textTertiary)
          .lineSpacing(3)
      }

      Spacer()
    }
    .padding(OmiSpacing.lg)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.sectionRadius, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.sectionRadius, style: .continuous)
            .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    )
  }
}

struct OnboardingSelectableChip: View {
  let title: String
  let isSelected: Bool
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      Text(title)
        .font(.system(size: 14, weight: .semibold))
        .foregroundColor(isSelected ? .black : OmiColors.textSecondary)
        .padding(.horizontal, OmiSpacing.lg)
        .padding(.vertical, OmiSpacing.sm)
        .background(
          Capsule()
            .fill(isSelected ? Color.white : OmiColors.backgroundSecondary)
        )
        .overlay(
          Capsule()
            .stroke(Color.white.opacity(isSelected ? 0 : 0.08), lineWidth: 1)
        )
    }
    .buttonStyle(.plain)
  }
}
