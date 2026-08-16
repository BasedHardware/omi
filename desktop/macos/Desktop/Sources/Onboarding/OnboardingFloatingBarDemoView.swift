import AppKit
import Combine
import OmiTheme
import SwiftUI

/// Onboarding step: prompts user to press ⌘+Enter, then activates the real
/// floating bar at the top of the screen. Shows Continue after the AI responds.
struct OnboardingFloatingBarDemoView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var chatProvider: ChatProvider
  var stepIndex: Int
  var totalSteps: Int
  var onComplete: () -> Void
  var onSkip: () -> Void
  var onForceComplete: (() -> Void)?

  @ObservedObject private var shortcutSettings = ShortcutSettings.shared
  @State private var barActivated = false
  @State private var showContinue = false
  /// Shortcut tokens (e.g. "⌘", "O") currently held down, so their keycaps
  /// light up while pressed and turn off on release.
  @State private var pressedTokens: Set<String> = []
  @State private var mainKeyDown = false
  @State private var keyLightMonitor: Any?
  @State private var demoQuerySent = false

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        OnboardingLogoMark(onForceComplete: onForceComplete)

        Spacer()

        Button(action: onSkip) {
          Text("Skip")
            .font(.system(size: 13))
            .foregroundColor(Ink.secondary)
        }
        .buttonStyle(.plain)
      }
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.vertical, OmiSpacing.lg)

      GlassSeparator()

      OnboardingProgressBar(stepIndex: stepIndex, totalSteps: totalSteps)
        .frame(maxWidth: .infinity, alignment: .center)
        .padding(.top, OmiSpacing.xl)

      // Keep the header/progress chrome fixed. The interactive content is
      // centered when it fits and becomes vertically scrollable when a compact
      // display or expanded response would otherwise clip the action row.
      OnboardingContentWithPinnedActions {
        VStack(spacing: OmiSpacing.xxl) {
          VStack(spacing: OmiSpacing.md) {
            if !barActivated {
              Text("Omi sees your screen and gives you hyper-personalized responses")
                .inkStyle(InkType.stepHeadline, color: Ink.primary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 560)

              Text("Press this shortcut to try it.")
                .inkStyle(InkType.prose, color: Ink.secondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            } else {
              Text("Omi is answering 'Which computer should I buy?' in the floating bar")
                .inkStyle(InkType.stepHeadline, color: Ink.primary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            }
          }

          if !barActivated {
            VStack(spacing: OmiSpacing.md) {
              HStack(spacing: OmiSpacing.xs) {
                ForEach(Array(shortcutSettings.askOmiShortcut.displayTokens.enumerated()), id: \.offset) {
                  index, symbol in
                  if index > 0 {
                    Text("+")
                      .font(.system(size: 15, weight: .medium))
                      .foregroundColor(Ink.secondary)
                  }
                  keyCap(symbol, isPressed: pressedTokens.contains(symbol))
                }
              }

              Text("Omi answers in the floating bar at the top of your screen.")
                .inkStyle(InkType.statusLabel, color: Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.top, OmiSpacing.xxs)
            .transition(.opacity)
          } else {
            MacLineupPreview()
              .frame(maxWidth: 980)
              .transition(.opacity.combined(with: .move(edge: .bottom)))
          }

        }
        .frame(maxWidth: 980)
      } actions: {
        // Back/Continue stays visible while the response preview scrolls.
        HStack(spacing: OmiSpacing.md) {
          OnboardingBackButton()

          if showContinue {
            Button(action: onComplete) {
              Text("Continue")
            }
            .buttonStyle(InkButtonStyle(kind: .primary))
            .keyboardShortcut(.defaultAction)
            .transition(.move(edge: .bottom).combined(with: .opacity))
          }
        }
        .frame(maxWidth: 980)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .onAppear {
      // Set up the real floating bar (creates the window if needed)
      FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
      FloatingControlBarManager.shared.barState?.switchAIDraft(to: .onboardingFloating)
      // Use the same global shortcut flow as the normal app so onboarding
      // behaves like production when the user presses Cmd+Enter.
      GlobalShortcutManager.shared.registerShortcuts()
      installKeyLightMonitor()
    }
    .onDisappear {
      removeKeyLightMonitor()
      FloatingControlBarManager.shared.barState?.onboardingBarGlow = false
      // Close the AI conversation panel on the floating bar so the next step starts clean
      if FloatingControlBarManager.shared.barState?.showingAIConversation == true {
        FloatingControlBarManager.shared.toggleAIInput()
      }
    }
    .onChange(of: barActivated) { _, activated in
      if activated {
        FloatingControlBarManager.shared.barState?.onboardingBarGlow = true
        Task { await waitForResponse() }
      }
    }
    .onReceive(Timer.publish(every: 0.25, on: .main, in: .common).autoconnect()) { _ in
      guard !barActivated,
        FloatingControlBarManager.shared.barState?.showingAIConversation == true
      else { return }
      OmiMotion.withGated(.spring(response: 0.4, dampingFraction: 0.8)) {
        barActivated = true
      }
    }
  }

  // MARK: - Response Observer

  /// Poll the floating bar state until the AI finishes responding.
  @MainActor
  private func waitForResponse() async {
    guard let barState = FloatingControlBarManager.shared.barState else { return }
    // Poll every 0.5s for up to 60s
    for _ in 0..<120 {
      try? await Task.sleep(nanoseconds: 500_000_000)
      if barState.showingAIResponse,
        let msg = barState.currentAIMessage(from: FloatingControlBarManager.shared.sharedFloatingProvider),
        !msg.isStreaming
      {
        OmiMotion.withGated(.easeInOut(duration: 0.3)) {
          showContinue = true
        }
        return
      }
    }
    // Timeout — show Continue anyway
    OmiMotion.withGated(.easeInOut(duration: 0.3)) {
      showContinue = true
    }
  }

  // MARK: - Live key highlighting

  /// Watches modifier + key events so the on-screen keycaps light up while the
  /// matching key is physically held and turn off on release.
  private func installKeyLightMonitor() {
    guard keyLightMonitor == nil else { return }
    keyLightMonitor = NSEvent.addLocalMonitorForEvents(
      matching: [.flagsChanged, .keyDown, .keyUp]
    ) { event in
      updatePressedTokens(from: event)
      return event
    }
  }

  private func removeKeyLightMonitor() {
    if let keyLightMonitor {
      NSEvent.removeMonitor(keyLightMonitor)
    }
    keyLightMonitor = nil
    pressedTokens = []
    mainKeyDown = false
  }

  private func updatePressedTokens(from event: NSEvent) {
    let shortcut = shortcutSettings.askOmiShortcut
    // Held modifiers, derived live from the event's flags.
    let liveFlags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
    var tokens = Set(ShortcutSettings.KeyboardShortcut.modifierTokens(for: liveFlags))

    // The non-modifier key (e.g. "O", "↩"): track its own down/up.
    if let keyCode = shortcut.keyCode, let keyDisplay = shortcut.keyDisplay {
      switch event.type {
      case .keyDown where event.keyCode == keyCode:
        mainKeyDown = true
      case .keyUp where event.keyCode == keyCode:
        mainKeyDown = false
      default:
        break
      }
      if mainKeyDown {
        tokens.insert(keyDisplay)
      }
    }

    // Only light caps that belong to this shortcut.
    pressedTokens = tokens.intersection(Set(shortcut.displayTokens))

    // The shortcut now opens the main app (typing moved out of the floating
    // bar), so the demo sends the sample question itself the moment the full
    // shortcut is pressed — the floating bar then shows the live answer.
    if !demoQuerySent, pressedTokens == Set(shortcut.displayTokens), !shortcut.displayTokens.isEmpty {
      demoQuerySent = true
      FloatingControlBarManager.shared.openAIInputWithQuery("Which computer should I buy?")
    }
  }

  // MARK: - Key Cap

  /// A keycap on glass: a wash with a hairline outline, inverting to an `Ink.primary` fill with an
  /// `Ink.surface` glyph while the key is held. The inversion is the whole affordance — a glow or a
  /// black drop shadow reads as dirt on a light panel.
  private func keyCap(_ key: String, isPressed: Bool = false) -> some View {
    Text(key)
      .font(.system(size: 15, weight: .medium, design: .rounded))
      .foregroundColor(isPressed ? Ink.surface : Ink.primary)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
          .fill(isPressed ? Ink.primary : Ink.rowFill)
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
              .strokeBorder(isPressed ? Color.clear : Ink.hairline, lineWidth: 1)
          )
      )
      .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isPressed)
  }
}

private struct MacLineupPreview: View {
  private static let lineupImage: NSImage? = {
    guard let url = Bundle.resourceBundle.url(forResource: "onboarding_mac_lineup", withExtension: "png") else {
      return nil
    }
    return NSImage(contentsOf: url)
  }()

  var body: some View {
    Group {
      if let nsImage = Self.lineupImage {
        Image(nsImage: nsImage)
          .resizable()
          .interpolation(.high)
          .scaledToFit()
          .clipShape(RoundedRectangle(cornerRadius: PageGlass.cardRadius, style: .continuous))
      } else {
        Text("Mac lineup image unavailable")
          .inkStyle(InkType.rowCopy, color: Ink.secondary)
          .frame(maxWidth: .infinity)
          .frame(height: 280)
          .glassCard()
      }
    }
  }
}
