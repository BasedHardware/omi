import OmiDesign
import SwiftUI

/// Something that needs a decision, as a raised card (Home's "For you" items, the memory review
/// entry; the Iris "Want me to handle it?" card): a small colored kicker that says what kind of
/// item it is, the title, one line of context, and pill buttons when there are two or more
/// choices. Tapping the card itself does the item's main thing. No swipe: a sideways drag would
/// fight the swipe between Home, Tasks and Memories.
public struct DecisionCard: View {
    public struct Kicker {
        let symbol: String
        let text: String
        let color: Color

        public init(symbol: String, text: String, color: Color) {
            self.symbol = symbol
            self.text = text
            self.color = color
        }
    }

    public struct Pill: Identifiable {
        let title: String
        var isPrimary = false
        let action: () -> Void
        public var id: String {
            title
        }

        public init(title: String, isPrimary: Bool = false, action: @escaping () -> Void) {
            self.title = title
            self.isPrimary = isPrimary
            self.action = action
        }
    }

    let kicker: Kicker
    let title: String
    let subtitle: String
    /// Where it comes from, one quiet line under the context ("From: Q4 roadmap with Anna, Tue").
    var source: String?
    /// Omi is working: the kicker's glyph breathes.
    var pulses = false
    let pills: [Pill]
    let onTap: (() -> Void)?
    /// In the chat thread: the bubbles' family (their radius, no edge), one line each for the
    /// title and the context, at most two pills.
    var compact = false

    public init(
        kicker: Kicker, title: String, subtitle: String, source: String? = nil, pulses: Bool = false, pills: [Pill],
        compact: Bool = false, onTap: (() -> Void)?
    ) {
        self.kicker = kicker
        self.title = title
        self.subtitle = subtitle
        self.source = source
        self.pulses = pulses
        self.pills = compact ? Array(pills.prefix(2)) : pills
        self.compact = compact
        self.onTap = onTap
    }

    private var radius: CGFloat {
        compact ? DS.Radius.bubble : DS.Radius.card
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: compact ? DS.Spacing.xs + 2 : DS.Spacing.sm) {
            HStack(spacing: compact ? DS.Spacing.xs : 6) {
                Image(systemName: kicker.symbol)
                    .font(.system(size: compact ? 11 : 12, weight: .semibold))
                    .symbolEffect(.pulse, isActive: pulses)
                Text(kicker.text)
                    .font(compact ? .caption.weight(.semibold) : .footnote.weight(.semibold))
            }
            .foregroundStyle(kicker.color)
            .accessibilityElement(children: .combine)
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(compact ? DS.Typography.callout.weight(.medium) : .body.weight(.medium))
                    .foregroundStyle(DS.Palette.ink)
                    .lineLimit(compact ? 1 : 2)
                    .fixedSize(horizontal: false, vertical: true)
                if !subtitle.isEmpty {
                    Text(subtitle)
                        .font(compact ? DS.Typography.caption : DS.Typography.callout)
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .lineLimit(compact ? 1 : 2)
                }
                if let source, !source.isEmpty {
                    Text(source)
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkTertiary)
                        .lineLimit(1)
                        .padding(.top, 1)
                }
            }
            if !pills.isEmpty {
                HStack(spacing: DS.Spacing.sm) {
                    ForEach(pills) { pill in
                        Button {
                            DSHaptics.tap(.light)
                            pill.action()
                        } label: {
                            Text(pill.title)
                                .font(compact ? .footnote.weight(.semibold) : .subheadline.weight(.semibold))
                                .lineLimit(1)
                                .foregroundStyle(pill.isPrimary ? DS.Palette.onAccent : DS.Palette.ink)
                                .padding(.horizontal, DS.Spacing.md)
                                .padding(.vertical, compact ? 6 : 7)
                                .background(pill.isPrimary ? DS.Palette.ink : Color.clear, in: Capsule())
                                .overlay {
                                    if !pill.isPrimary { Capsule().strokeBorder(DS.Palette.fill, lineWidth: 1) }
                                }
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.top, 2)
            }
        }
        .multilineTextAlignment(.leading)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, compact ? 14 : DS.Spacing.lg)
        .padding(.vertical, compact ? DS.Spacing.sm + 2 : DS.Spacing.md)
        .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
        .overlay {
            if !compact {
                RoundedRectangle(cornerRadius: radius, style: .continuous).strokeBorder(DS.Palette.cardStroke, lineWidth: 0.5)
            }
        }
        .contentShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
        .onTapGesture { onTap?() }
        .accessibilityAddTraits(onTap == nil ? [] : .isButton)
    }
}
