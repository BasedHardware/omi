import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// First run, after consent (PLAN.md §4.6). About you (name, language, how you heard of Omi),
/// then your Omi: with one, pair it, learn its light and whisper to it; without one the iPhone
/// microphone stands in. Either way the voice sample is recorded through what the user will
/// actually wear, then permissions and "Setting up your Omi".
///
/// The look is calm and dark: a quiet label over a large headline, at most one line under it,
/// soft rounded boxes, the pendant still (nothing blinks or pulses), a thin progress line and one
/// white button at the same place on every step. Every step fits an iPhone 15 Pro without
/// scrolling. Steps change in about 0.3 s; only the content changes, the chrome stays.
public struct OnboardingScreen: View {
    @State private var store: OnboardingStore
    @Environment(SessionStore.self) private var session
    @Environment(CaptureStore.self) private var capture
    /// The step on screen before the current one: a step further on slides in from the right,
    /// going back from the left.
    @State private var previousStep: OnboardingStore.Step

    public init(store: OnboardingStore) {
        _store = State(initialValue: store)
        _previousStep = State(initialValue: store.step)
    }

    /// Quick and crisp: no bounce, done in about 0.3 s, so a tap feels answered at once.
    static let stepAnimation = Animation.spring(duration: 0.3, bounce: 0)

    public var body: some View {
        VStack(spacing: 0) {
            if store.step != .setup, store.step != .ready { chrome }
            Group {
                switch store.step {
                case .name: NameStep(store: store)
                case .language: LanguageStep(store: store)
                case .foundOmi: SourceStep(store: store)
                case .hasOmi: HasOmiStep(store: store)
                case .pair: PairStep(store: store)
                case .lights: LightsStep(onContinue: store.next)
                case .hello: HelloStep(store: store)
                case .voice: VoiceStep(store: store)
                case .askOmi, .voiceReply, .doublePress, .watch: OmiButtonAndWatchSteps(store: store)
                case .permissions: PermissionsStep(onContinue: store.next)
                case .setup: SetupStep(onFinished: { session.saveOnboardingCompleted(); store.next() })
                case .ready: ReadyFlow(name: store.givenName, hasOmi: store.hasOmi == true) { topic in
                    session.settingsAfterIntroduction = topic
                    session.completeOnboarding()
                }
                }
            }
            .id(store.step)
            // The old step is gone in a tenth of a second, so two headlines never sit on top of
            // each other; the new one slides in from the side it comes from.
            .transition(.asymmetric(
                insertion: .opacity.combined(with: .offset(x: store.step.rawValue >= previousStep.rawValue ? 24 : -24))
                    .animation(Self.stepAnimation.delay(0.06)),
                removal: .opacity.animation(.easeIn(duration: 0.1))
            ))
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .animation(Self.stepAnimation, value: store.step)
        .onChange(of: store.step) { _, step in previousStep = step }
        // Onboarding is always dark and pure black, whatever the app's appearance (design decision, 2026-10-07).
        .background(Color.black.ignoresSafeArea())
        .environment(\.colorScheme, .dark)
        .onDisappear { store.voice?.stop() }
        // Replayed from Settings: what is said here is practice, not a conversation. The app
        // restarts capture from a connected Omi when it opens again.
        .task { if capture.isLive { await capture.stop() } }
        #if DEBUG
            .task {
                // -omiOnboardingAutoAdvance <seconds>: walks forward on its own, then back once
                // (simulator QA of the step transitions, recorded without tapping).
                let seconds = UserDefaults.standard.double(forKey: "omiOnboardingAutoAdvance")
                guard seconds > 0 else { return }
                for forward in [true, true, true, false] {
                    try? await Task.sleep(for: .seconds(seconds))
                    if forward { store.next() } else { store.back() }
                }
            }
        #endif
    }

    /// Back on the left, the progress line across. Back stays in its slot when hidden so the
    /// line never jumps.
    private var chrome: some View {
        HStack(spacing: DS.Spacing.md) {
            Button {
                store.voice?.stop()
                store.back()
            } label: {
                Image(systemName: "chevron.left")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .frame(width: 36, height: 36)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .opacity(store.step == .name ? 0 : 1)
            .disabled(store.step == .name)
            .accessibilityLabel(L("back"))
            OnboardingProgress(value: store.progress)
            Color.clear.frame(width: 36, height: 1)
        }
        .frame(height: 36)
        .padding(.horizontal, DS.Spacing.lg)
        .padding(.top, DS.Spacing.sm)
    }
}

/// Wraps chips onto as many lines as needed.
struct FlowLayout: Layout {
    var spacing: CGFloat
    var alignment: HorizontalAlignment = .leading

    struct Row {
        var y: CGFloat
        var height: CGFloat
        var items: [(index: Int, x: CGFloat)]
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache _: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        return CGSize(width: proposal.width ?? 0, height: rows.last.map { $0.y + $0.height } ?? 0)
    }

    func placeSubviews(in bounds: CGRect, proposal _: ProposedViewSize, subviews: Subviews, cache _: inout ()) {
        for row in arrange(width: bounds.width, subviews: subviews) {
            let used = row.items.last.map { $0.x + subviews[$0.index].sizeThatFits(.unspecified).width } ?? 0
            let inset = alignment == .center ? (bounds.width - used) / 2 : 0
            for item in row.items {
                subviews[item.index].place(
                    at: CGPoint(x: bounds.minX + inset + item.x, y: bounds.minY + row.y),
                    proposal: .unspecified
                )
            }
        }
    }

    private func arrange(width: CGFloat, subviews: Subviews) -> [Row] {
        var rows: [Row] = []
        var current = Row(y: 0, height: 0, items: [])
        var x: CGFloat = 0
        for (index, subview) in subviews.enumerated() {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > width, !current.items.isEmpty {
                rows.append(current)
                current = Row(y: current.y + current.height + spacing, height: 0, items: [])
                x = 0
            }
            current.items.append((index, x))
            x += size.width + spacing
            current.height = max(current.height, size.height)
        }
        if !current.items.isEmpty { rows.append(current) }
        return rows
    }
}
