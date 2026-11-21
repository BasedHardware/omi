import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// One continuous line, no segments: a count of steps reads as "this will take a while".
struct OnboardingProgress: View {
    let value: Double

    var body: some View {
        GeometryReader { proxy in
            Capsule().fill(DS.Palette.ink.opacity(0.12))
                .overlay(alignment: .leading) {
                    Capsule().fill(DS.Palette.ink).frame(width: max(6, proxy.size.width * value))
                        .animation(OnboardingScreen.stepAnimation, value: value)
                }
        }
        .frame(height: 3)
        .accessibilityElement()
        .accessibilityLabel(L("nativeOnboardingProgress", String(Int(value * 100))))
    }
}

/// A quiet label naming the part of the setup, a large headline, at most one muted line under it.
/// `centered` for the hero steps (an image below), leading for the others.
struct OnboardingHeader: View {
    let kicker: String
    let title: String
    var subtitle: String?
    var centered = false

    var body: some View {
        VStack(alignment: centered ? .center : .leading, spacing: DS.Spacing.sm) {
            Text(kicker)
                .font(.footnote.weight(.semibold))
                .foregroundStyle(DS.Palette.inkTertiary)
            Text(title)
                .font(DS.Typography.display)
                .foregroundStyle(DS.Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
                .contentTransition(.opacity)
            if let subtitle {
                Text(subtitle)
                    .font(.body)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, DS.Spacing.xxs)
                    .contentTransition(.opacity)
            }
        }
        .multilineTextAlignment(centered ? .center : .leading)
        .frame(maxWidth: .infinity, alignment: centered ? .center : .leading)
        .padding(.horizontal, DS.Spacing.gutter)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
    }
}

extension View {
    /// The onboarding's one surface: a softly filled rounded box with a hairline edge.
    func onboardingCard(padding: CGFloat = DS.Spacing.lg) -> some View {
        self.padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.Palette.ink.opacity(0.05), in: RoundedRectangle(cornerRadius: DS.Radius.card, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: DS.Radius.card, style: .continuous)
                    .strokeBorder(DS.Palette.ink.opacity(0.08), lineWidth: 1)
            }
    }
}

/// A button of the step.
struct StepButton {
    let title: String
    var isEnabled = true
    /// A way out (skip) rather than the step's goal: drawn quieter, without the arrow.
    var isSecondary = false
    let action: () -> Void
}

/// Header, content, and the buttons pinned to the bottom: one primary button, and under it the
/// slot of the quiet way out, kept even when empty so the button never moves between steps.
/// Content only scrolls where Dynamic Type makes it taller than the screen.
struct OnboardingLayout<Content: View>: View {
    let kicker: String
    let title: String
    var subtitle: String?
    var button: StepButton?
    var secondary: StepButton?
    var scrolls = true
    /// Headline centered over a hero image instead of leading.
    var centered = false
    /// A quiet line over the buttons while something happens on its own.
    var status: String?
    @ViewBuilder let content: Content

    static var secondaryHeight: CGFloat {
        44
    }

    var body: some View {
        VStack(spacing: 0) {
            if scrolls {
                ScrollView {
                    stack.padding(.bottom, DS.Spacing.lg)
                }
                .scrollIndicators(.hidden)
                .scrollBounceBehavior(.basedOnSize)
            } else {
                stack.frame(maxHeight: .infinity, alignment: .top)
            }
            buttons
        }
    }

    private var stack: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.section) {
            OnboardingHeader(kicker: kicker, title: title, subtitle: subtitle, centered: centered)
                .padding(.top, DS.Spacing.lg)
            content
        }
    }

    @ViewBuilder
    private var buttons: some View {
        if button != nil || secondary != nil || status != nil {
            VStack(spacing: DS.Spacing.xs) {
                if let status {
                    OmiStatusLine(status).padding(.bottom, DS.Spacing.md).transition(.opacity)
                }
                if let button { OnboardingButton(button) }
                Group {
                    if let secondary {
                        Button(secondary.title, action: secondary.action)
                            .font(.callout.weight(.semibold))
                            .foregroundStyle(DS.Palette.inkSecondary)
                            .disabled(!secondary.isEnabled)
                            .accessibilityIdentifier("onboarding.secondary")
                    } else {
                        Color.clear
                    }
                }
                .frame(maxWidth: .infinity, minHeight: Self.secondaryHeight, maxHeight: Self.secondaryHeight)
            }
            .padding(.horizontal, DS.Spacing.gutter)
            .padding(.top, DS.Spacing.sm)
            .padding(.bottom, DS.Spacing.sm)
        }
    }
}

/// White pill with a trailing arrow; quieter when it is a way out.
struct OnboardingButton: View {
    let model: StepButton

    init(_ model: StepButton) {
        self.model = model
    }

    var body: some View {
        Group {
            if model.isSecondary {
                Button(action: model.action) { Text(model.title) }
                    .buttonStyle(.omiSecondary)
            } else {
                Button(action: model.action) {
                    HStack(spacing: DS.Spacing.sm) {
                        Text(model.title)
                        Image(systemName: "arrow.right").font(.body.weight(.semibold))
                    }
                }
                .buttonStyle(.omiPrimary)
            }
        }
        .disabled(!model.isEnabled)
        .accessibilityIdentifier("onboarding.continue")
    }
}

/// One line of a choice list: icon, title, and a check when chosen. No detail lines: the step's
/// one subtitle explains, the rows only name.
struct ChoiceRow: View {
    let symbol: String
    let title: String
    var selected = false
    let action: () -> Void

    var body: some View {
        Button {
            DSHaptics.selection()
            action()
        } label: {
            HStack(spacing: DS.Spacing.md) {
                Image(systemName: symbol)
                    .font(.title3)
                    .foregroundStyle(selected ? DS.Palette.ink : DS.Palette.inkSecondary)
                    .frame(width: 28)
                Text(title)
                    .font(.body.weight(selected ? .semibold : .regular))
                    .foregroundStyle(DS.Palette.ink)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .font(.title3)
                    .foregroundStyle(selected ? DS.Palette.agent : DS.Palette.ink.opacity(0.25))
                    .contentTransition(.symbolEffect(.replace))
            }
            .padding(.horizontal, DS.Spacing.lg)
            .frame(minHeight: 56)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? [.isSelected] : [])
    }
}

/// Rows in one card, with hairlines between them.
struct RowList<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        VStack(spacing: 0) {
            Group(subviews: content) { rows in
                ForEach(Array(rows.enumerated()), id: \.offset) { index, row in
                    row
                    if index < rows.count - 1 {
                        Rectangle()
                            .fill(DS.Palette.ink.opacity(0.08))
                            .frame(height: 0.5)
                            .padding(.leading, DS.Spacing.lg + 28 + DS.Spacing.md)
                    }
                }
            }
        }
        .onboardingCard(padding: 0)
        .padding(.horizontal, DS.Spacing.gutter)
    }
}

/// One line of status under a step: what it says, its symbol and colour.
struct StatusLine {
    let text: String
    let symbol: String
    let tint: Color

    init(_ text: String, _ symbol: String, _ tint: Color) {
        self.text = text
        self.symbol = symbol
        self.tint = tint
    }

    var view: some View {
        Label(text, systemImage: symbol)
            .font(.subheadline.weight(.medium))
            .foregroundStyle(tint)
            .frame(maxWidth: .infinity)
            .multilineTextAlignment(.center)
            .contentTransition(.opacity)
    }
}

/// The pendant, still: no rings, no pulse. A small badge can sit on it (a check, "1×").
struct PendantImage<Badge: View>: View {
    var size: CGFloat = 140
    @ViewBuilder var badge: Badge

    var body: some View {
        OmiMedia.device
            .resizable()
            .scaledToFit()
            .frame(width: size, height: size)
            .overlay(alignment: .topTrailing) { badge.offset(x: -size * 0.04, y: size * 0.04) }
            .frame(maxWidth: .infinity)
            .accessibilityHidden(true)
    }
}

extension PendantImage where Badge == EmptyView {
    init(size: CGFloat = 140) {
        self.size = size
        badge = EmptyView()
    }
}

/// The Omi steps work with a connected Omi: one paired but not connected (a replay, or a step
/// opened directly) is connected on arrival.
struct ConnectsPairedOmi: ViewModifier {
    @Environment(DeviceStore.self) private var devices

    func body(content: Content) -> some View {
        content.task {
            if devices.paired != nil, devices.connection == .disconnected { devices.start() }
        }
    }
}

extension View {
    func connectsPairedOmi() -> some View {
        modifier(ConnectsPairedOmi())
    }
}
