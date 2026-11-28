import OmiDesign
import StoreKit
import SwiftUI

/// "Setting up your Omi": steps arrive one by one, each with a barely-there tick, and are checked
/// off with a light one, about ten seconds in all. The rating ask comes right after the first
/// step, while there is plenty of time left, as a system alert (Liquid Glass on iOS 26); the steps
/// keep running underneath and the flow never finishes while it is open.
struct SetupStep: View {
    let onFinished: () -> Void
    @Environment(\.requestReview) private var requestReview
    @State private var shown = 0
    @State private var completed = 0
    @State private var asksForReview = false
    @State private var askedForReview = false

    private struct Item {
        let key: String
        let symbol: String
        /// How long this one takes, so the list does not tick like a metronome.
        let seconds: Double
    }

    private let items = [
        Item(key: "nativeSetupProfile", symbol: "person.crop.circle", seconds: 1.3),
        Item(key: "nativeSetupVoice", symbol: "waveform", seconds: 1.8),
        Item(key: "nativeSetupLanguage", symbol: "character.bubble", seconds: 1.4),
        Item(key: "nativeSetupMemory", symbol: "brain", seconds: 1.9),
        Item(key: "nativeSetupSummaries", symbol: "text.alignleft", seconds: 1.5),
        Item(key: "nativeSetupFinal", symbol: "checkmark.seal", seconds: 1.4),
    ]
    static let reviewAfterStep = 1

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            OnboardingHeader(kicker: L("nativeKickerAlmostDone"), title: L("nativeSetupTitle"), subtitle: L("nativeSetupSubtitle"))
                .padding(.top, DS.Spacing.section + 44)
                .padding(.bottom, DS.Spacing.xl)
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: DS.Spacing.lg) {
                        ForEach(Array(items.prefix(shown).enumerated()), id: \.offset) { index, item in
                            row(item, index: index)
                                .id(index)
                                .transition(.asymmetric(insertion: .move(edge: .bottom).combined(with: .opacity), removal: .opacity))
                        }
                    }
                    .padding(.horizontal, DS.Spacing.gutter)
                    .padding(.bottom, DS.Spacing.section)
                }
                .scrollIndicators(.hidden)
                .onChange(of: shown) { _, shown in
                    withAnimation(DS.Motion.standard) { proxy.scrollTo(shown - 1, anchor: .bottom) }
                }
            }
            progressLine
        }
        .task { await run() }
        .alert(L("nativeReviewTitle"), isPresented: $asksForReview) {
            Button(L("nativeReviewYes")) { requestReview() }
            Button(L("nativeReviewNo"), role: .cancel) {}
        } message: {
            Text(L("nativeReviewBody"))
        }
    }

    private func row(_ item: Item, index: Int) -> some View {
        HStack(spacing: DS.Spacing.md) {
            ZStack {
                if index < completed {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(DS.Palette.agent)
                        .transition(.scale.combined(with: .opacity))
                } else {
                    ProgressView().tint(DS.Palette.agent)
                }
            }
            .font(.title2)
            .frame(width: 28, height: 28)
            Image(systemName: item.symbol)
                .font(.body)
                .foregroundStyle(index < completed ? DS.Palette.inkSecondary : DS.Palette.ink)
                .frame(width: 24)
            Text(L(item.key))
                .font(.body.weight(.medium))
                .foregroundStyle(index < completed ? DS.Palette.inkSecondary : DS.Palette.ink)
            Spacer(minLength: 0)
        }
        .animation(DS.Motion.snappy, value: completed)
    }

    private var progressLine: some View {
        GeometryReader { proxy in
            Capsule().fill(DS.Palette.ink.opacity(0.1))
                .overlay(alignment: .leading) {
                    Capsule().fill(DS.Palette.agent)
                        .frame(width: proxy.size.width * Double(completed) / Double(items.count))
                        .animation(.easeOut(duration: 0.6), value: completed)
                }
        }
        .frame(height: 3)
        .padding(.horizontal, DS.Spacing.gutter)
        .padding(.bottom, DS.Spacing.xl)
    }

    private func run() async {
        for (index, item) in items.enumerated() {
            withAnimation(DS.Motion.standard) { shown = index + 1 }
            DSHaptics.soft()
            try? await Task.sleep(for: .seconds(item.seconds))
            withAnimation(DS.Motion.snappy) { completed = index + 1 }
            DSHaptics.tap(.light)
            if completed == Self.reviewAfterStep, !askedForReview {
                askedForReview = true
                try? await Task.sleep(for: .milliseconds(400))
                asksForReview = true
            }
            try? await Task.sleep(for: .milliseconds(250))
        }
        // Never finish while the rating ask is open.
        while asksForReview {
            try? await Task.sleep(for: .milliseconds(200))
        }
        DSHaptics.success()
        try? await Task.sleep(for: .milliseconds(900))
        onFinished()
    }
}
