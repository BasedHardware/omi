import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// After "Setting up your Omi": the "You're ready" moment, then (if wanted) the short introduction.
/// `onFinished` lands on Home; its argument is a Settings section to open there (the For you
/// card's "Choose how often"), or nil.
struct ReadyFlow: View {
    let name: String
    let hasOmi: Bool
    let onFinished: (String?) -> Void
    @State private var showsTour = false

    var body: some View {
        ZStack {
            if showsTour {
                IntroTourScreen(onFinished: onFinished)
                    .transition(.asymmetric(insertion: .move(edge: .trailing).combined(with: .opacity), removal: .opacity))
            } else {
                ReadyStep(
                    name: name, hasOmi: hasOmi,
                    onTour: { withAnimation(DS.Motion.standard) { showsTour = true } },
                    onSkip: { onFinished(nil) }
                )
                .transition(.opacity)
            }
        }
    }
}

/// "You're ready, Ada." A ring draws itself around a check, a soft tap, one line on what
/// happens now. Centered, with air: the calm end of setup.
struct ReadyStep: View {
    let name: String
    let hasOmi: Bool
    let onTour: () -> Void
    let onSkip: () -> Void
    @State private var drawn = false

    private var firstName: String {
        name.split(separator: " ").first.map(String.init) ?? ""
    }

    var body: some View {
        VStack(spacing: 0) {
            Spacer(minLength: DS.Spacing.section)
            ReadyMark(drawn: drawn)
                .padding(.bottom, DS.Spacing.section + DS.Spacing.lg)
            VStack(spacing: DS.Spacing.md) {
                Text(firstName.isEmpty ? L("nativeReadyTitleNoName") : L("nativeReadyTitle", firstName))
                    .font(DS.Typography.display)
                    .foregroundStyle(DS.Palette.ink)
                Text(hasOmi ? L("nativeReadyBody") : L("nativeReadyBodyPhone"))
                    .font(DS.Typography.body)
                    .foregroundStyle(DS.Palette.inkSecondary)
            }
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, DS.Spacing.section)
            .opacity(drawn ? 1 : 0)
            .offset(y: drawn ? 0 : 8)
            if hasOmi {
                OmiChip(L("nativeReadyListening"), systemImage: "waveform", tint: DS.Palette.agent)
                    .padding(.top, DS.Spacing.xl)
                    .opacity(drawn ? 1 : 0)
            }
            Spacer(minLength: DS.Spacing.section)
            VStack(spacing: DS.Spacing.xs) {
                OnboardingButton(StepButton(title: L("nativeReadyTour"), action: onTour))
                    .accessibilityIdentifier("ready.tour")
                Button(L("nativeReadySkip"), action: onSkip)
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .accessibilityIdentifier("ready.skip")
            }
            .padding(.horizontal, DS.Spacing.gutter)
            .padding(.bottom, DS.Spacing.md)
            .opacity(drawn ? 1 : 0)
        }
        .frame(maxWidth: .infinity)
        .task {
            try? await Task.sleep(for: .milliseconds(250))
            withAnimation(.easeOut(duration: 0.9)) { drawn = true }
            try? await Task.sleep(for: .milliseconds(650))
            DSHaptics.success()
        }
    }
}

/// A thin ring that draws itself (hairline gray warming into Omi blue) around a check, with a
/// soft blue glow behind it.
private struct ReadyMark: View {
    let drawn: Bool

    var body: some View {
        ZStack {
            Circle()
                .fill(DS.Glow.live)
                .frame(width: 150, height: 150)
                .blur(radius: 40)
                .opacity(drawn ? 0.8 : 0)
            Circle()
                .stroke(DS.Palette.hairline, lineWidth: DS.Stroke.hero)
                .frame(width: 128, height: 128)
            Circle()
                .trim(from: 0, to: drawn ? 1 : 0)
                .stroke(
                    AngularGradient(colors: [DS.Palette.inkTertiary.opacity(0.4), DS.Palette.agent], center: .center),
                    style: StrokeStyle(lineWidth: DS.Stroke.hero * 1.5, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))
                .frame(width: 128, height: 128)
            Image(systemName: "checkmark")
                .font(.system(size: 40, weight: .light))
                .foregroundStyle(DS.Palette.ink)
                .scaleEffect(drawn ? 1 : 0.6)
                .opacity(drawn ? 1 : 0)
        }
        .frame(width: 180, height: 180)
        .accessibilityHidden(true)
    }
}

// MARK: The introduction

/// Five short pages on how Omi works, each with a small live demo built from the app's own rows.
/// Skippable, swipeable. Also replayed on its own from Help.
public struct IntroTourScreen: View {
    let onFinished: (String?) -> Void
    @State private var page = 0

    /// `onFinished` gets a Settings section to open afterwards, or nil.
    public init(onFinished: @escaping (String?) -> Void) {
        self.onFinished = onFinished
    }

    static let pages = IntroPage.allCases

    public var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(L("nativeIntroKicker"))
                    .font(DS.Typography.label)
                    .tracking(DS.Tracking.label)
                    .textCase(.uppercase)
                    .foregroundStyle(DS.Palette.inkTertiary)
                Spacer()
                Button(L("skip")) { onFinished(nil) }
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .frame(minHeight: 44)
                    .accessibilityIdentifier("intro.skip")
            }
            .padding(.horizontal, DS.Spacing.gutter)
            .padding(.top, DS.Spacing.sm)
            TabView(selection: $page) {
                ForEach(Array(Self.pages.enumerated()), id: \.offset) { index, item in
                    IntroCard(page: item, isActive: page == index, onSetting: { onFinished("assistant") })
                        .tag(index)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never))
            .clipped()
            .animation(DS.Motion.standard, value: page)
            PageDots(count: Self.pages.count, current: page)
                .padding(.bottom, DS.Spacing.lg)
            OnboardingButton(StepButton(
                title: page == Self.pages.count - 1 ? L("nativeIntroDone") : L("nativeIntroNext"),
                action: {
                    if page < Self.pages.count - 1 {
                        withAnimation(DS.Motion.standard) { page += 1 }
                    } else {
                        onFinished(nil)
                    }
                }
            ))
            .padding(.horizontal, DS.Spacing.gutter)
            .padding(.bottom, DS.Spacing.md)
        }
        .background(CalmBackground().ignoresSafeArea())
        .onChange(of: page) { _, _ in DSHaptics.selection() }
        .task {
            #if DEBUG
                // -omiIntroPage <n>: open on a page (simulator QA).
                page = min(max(0, UserDefaults.standard.integer(forKey: "omiIntroPage")), Self.pages.count - 1)
            #endif
        }
    }
}

enum IntroPage: CaseIterable {
    case listen, learn, voices, forYou, handOver

    var title: String {
        switch self {
        case .listen: L("nativeIntroListenTitle")
        case .learn: L("nativeIntroLearnTitle")
        case .voices: L("nativeIntroVoicesTitle")
        case .forYou: L("nativeIntroForYouTitle")
        case .handOver: L("nativeIntroHandOverTitle")
        }
    }

    var body: String {
        switch self {
        case .listen: L("nativeIntroListenBody")
        case .learn: L("nativeIntroLearnBody")
        case .voices: L("nativeIntroVoicesBody")
        case .forYou: L("nativeIntroForYouBody")
        case .handOver: L("nativeIntroHandOverBody")
        }
    }
}

/// One page: the live demo on top, a serif title and a quiet line under it.
private struct IntroCard: View {
    let page: IntroPage
    let isActive: Bool
    let onSetting: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: DS.Spacing.xl) {
                demo
                    .frame(maxWidth: .infinity, minHeight: 230, alignment: .top)
                    .padding(.top, DS.Spacing.lg)
                VStack(spacing: DS.Spacing.sm) {
                    Text(page.title)
                        .font(DS.Typography.largeTitle)
                        .foregroundStyle(DS.Palette.ink)
                    Text(page.body)
                        .font(DS.Typography.body)
                        .foregroundStyle(DS.Palette.inkSecondary)
                }
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, DS.Spacing.sm)
                extra
            }
            .padding(.horizontal, DS.Spacing.gutter)
            .padding(.bottom, DS.Spacing.lg)
        }
        .scrollIndicators(.hidden)
        .scrollBounceBehavior(.basedOnSize)
    }

    @ViewBuilder
    private var demo: some View {
        switch page {
        case .listen: ListenDemo(isActive: isActive)
        case .learn: MemoryDemo(isActive: isActive)
        case .voices: VoicesDemo(isActive: isActive)
        case .forYou: ForYouDemo(isActive: isActive)
        case .handOver: HandOverDemo(isActive: isActive)
        }
    }

    @ViewBuilder
    private var extra: some View {
        switch page {
        case .forYou:
            Button(action: onSetting) {
                OmiChip(L("nativeIntroForYouSetting"), systemImage: "slider.horizontal.3", tint: DS.Palette.agent)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("intro.forYouSetting")
        case .handOver:
            VStack(alignment: .leading, spacing: DS.Spacing.md) {
                Label(L("nativeIntroOnItsOwn"), systemImage: "checkmark.circle")
                    .foregroundStyle(DS.Palette.ink)
                Label(L("nativeIntroAsksFirst"), systemImage: "hand.raised")
                    .foregroundStyle(DS.Palette.ink)
            }
            .font(DS.Typography.callout)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
        default:
            EmptyView()
        }
    }
}

/// Small dots under the pages; the current one is a short bar.
private struct PageDots: View {
    let count: Int
    let current: Int

    var body: some View {
        HStack(spacing: 6) {
            ForEach(0 ..< count, id: \.self) { index in
                Capsule()
                    .fill(index == current ? DS.Palette.ink : DS.Palette.ink.opacity(0.18))
                    .frame(width: index == current ? 18 : 6, height: 6)
            }
        }
        .animation(DS.Motion.snappy, value: current)
        .accessibilityElement()
        .accessibilityLabel(L("nativeIntroPage", String(current + 1), String(count)))
    }
}
