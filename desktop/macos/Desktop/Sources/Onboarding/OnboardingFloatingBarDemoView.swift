import SwiftUI
import AppKit
import OmiTheme

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

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                OnboardingLogoMark(onForceComplete: onForceComplete)

                Spacer()

                Button(action: onSkip) {
                    Text("Skip")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, OmiSpacing.xxl)
            .padding(.vertical, OmiSpacing.lg)

            Divider()
                .background(OmiColors.backgroundTertiary)

            OnboardingProgressDots(stepIndex: stepIndex, totalSteps: totalSteps)
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.top, OmiSpacing.xl)

            Spacer()

            // Content
            VStack(spacing: OmiSpacing.xxl) {
                VStack(spacing: OmiSpacing.md) {
                    if !barActivated {
                        Text("Omi sees your screen and gives you hyper-personalized responses")
                            .font(.system(size: 20, weight: .bold))
                            .foregroundColor(OmiColors.textPrimary)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: 560)

                        Text("Press this shortcut to open Ask Omi.")
                            .font(.system(size: 18, weight: .medium))
                            .foregroundColor(OmiColors.textSecondary)
                            .multilineTextAlignment(.center)
                    } else {
                        // One line, ending in an arrow that points up to the real
                        // floating bar at the top of the screen — once it activates
                        // many people never look up.
                        HStack(spacing: OmiSpacing.sm) {
                            Text("Type in the Floating Bar 'Which computer should I buy?'")
                                .font(.system(size: 24, weight: .bold))
                                .foregroundColor(OmiColors.textPrimary)
                                .lineLimit(1)
                                .fixedSize()

                            Image(systemName: "arrow.up")
                                .font(.system(size: 24, weight: .bold))
                                .foregroundColor(OmiColors.textPrimary)
                                // Tilt up-left so it points toward the bar/dock,
                                // which sits left of the text's trailing edge.
                                .rotationEffect(.degrees(-30))
                        }
                    }
                }

                if !barActivated {
                    VStack(spacing: OmiSpacing.md) {
                        HStack(spacing: OmiSpacing.xs) {
                            ForEach(Array(shortcutSettings.askOmiShortcut.displayTokens.enumerated()), id: \.offset) { index, symbol in
                                if index > 0 {
                                    Text("+")
                                        .font(.system(size: 15, weight: .medium))
                                        .foregroundColor(OmiColors.textTertiary)
                                }
                                keyCap(symbol, isPressed: pressedTokens.contains(symbol))
                            }
                        }

                        Text("Ask Omi opens at the top of your screen.")
                            .font(.system(size: 13))
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .padding(.top, OmiSpacing.xxs)
                    .transition(.opacity)
                } else {
                    MacLineupPreview()
                        .frame(maxWidth: 980)
                        .transition(.opacity.combined(with: .move(edge: .bottom)))
                }

            }
            .padding(.top, 88)
            .padding(.horizontal, OmiSpacing.page)

            Spacer()

            // Bottom row — back is always available; Continue appears after the AI responds
            HStack(spacing: OmiSpacing.md) {
                OnboardingBackButton()

                if showContinue {
                    Button(action: onComplete) {
                        Text("Continue")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundColor(.black)
                            .frame(maxWidth: 280)
                            .padding(.vertical, OmiSpacing.md)
                            .background(Color.white)
                            .cornerRadius(OmiChrome.smallControlRadius)
                    }
                    .buttonStyle(.plain)
                    .keyboardShortcut(.defaultAction)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .padding(.bottom, OmiSpacing.section)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OmiColors.backgroundPrimary)
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
                  FloatingControlBarManager.shared.barState?.showingAIConversation == true else { return }
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
               !msg.isStreaming {
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

    // MARK: - Key Cap

    private func keyCap(_ key: String, isPressed: Bool = false) -> some View {
        Text(key)
            .font(.system(size: 15, weight: .medium, design: .rounded))
            .foregroundColor(isPressed ? .black : OmiColors.textPrimary)
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
            .background(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                    .fill(isPressed ? Color.white : OmiColors.backgroundTertiary)
                    .overlay(
                        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                            .stroke(
                                isPressed ? Color.white : OmiColors.backgroundQuaternary.opacity(0.5),
                                lineWidth: 1
                            )
                    )
                    .shadow(
                        color: isPressed ? Color.white.opacity(0.5) : .black.opacity(0.2),
                        radius: isPressed ? 8 : 1,
                        x: 0,
                        y: isPressed ? 0 : 1
                    )
            )
            .animation(.easeOut(duration: 0.08), value: isPressed)
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
    }
}

private struct MacLineupPreview: View {
    private static let lineupImage: NSImage? = {
        guard let url = Bundle.resourceBundle.url(forResource: "onboarding_mac_lineup", withExtension: "png") else { return nil }
        return NSImage(contentsOf: url)
    }()

    var body: some View {
        Group {
            if let nsImage = Self.lineupImage {
                Image(nsImage: nsImage)
                    .resizable()
                    .interpolation(.high)
                    .scaledToFit()
                    .clipShape(RoundedRectangle(cornerRadius: OmiChrome.cardRadius, style: .continuous))
            } else {
                RoundedRectangle(cornerRadius: OmiChrome.cardRadius)
                    .fill(Color.white.opacity(0.06))
                    .frame(height: 280)
                    .overlay(
                        Text("Mac lineup image unavailable")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(OmiColors.textTertiary)
                    )
            }
        }
    }
}
