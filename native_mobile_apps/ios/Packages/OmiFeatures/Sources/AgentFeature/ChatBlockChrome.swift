import OmiCore
import OmiDesign
import SwiftUI

// The pieces every card shares: the card itself, the small heading above its text, the link
// card, the one button a card offers, and the line a block with no card stays readable as.

// MARK: - Chrome

/// The lines the cards cannot draw, when the cards replaced the body (otherwise the body already
/// carries them). A thinking line, a tool call, a type this client does not know: each stays
/// readable instead of vanishing.
struct ChatBlockFallbacks: View {
    @Environment(\.chatBubbleWidth) private var bubbleWidth
    let lines: [String]

    var body: some View {
        if !lines.isEmpty {
            VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                    Text(line)
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkTertiary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: bubbleWidth, alignment: .leading)
            .accessibilityIdentifier("chat.block.fallback")
        }
    }
}

/// The card every block draws on: the chat card color, a soft radius, and the file's own
/// padding. A card is tappable only when it leads somewhere.
struct ChatBlockCard<Content: View>: View {
    var onTap: (() -> Void)?
    @ViewBuilder var content: () -> Content

    var body: some View {
        let card = content()
            .padding(.horizontal, 14)
            .padding(.vertical, DS.Spacing.sm + 1)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: DS.Radius.bubble, style: .continuous))
        if let onTap {
            Button(action: onTap) { card }
                .buttonStyle(.plain)
                .contentShape(RoundedRectangle(cornerRadius: DS.Radius.bubble, style: .continuous))
        } else {
            card
        }
    }
}

/// What the card holds: its kind, in small caps, with the sign that goes with it.
struct ChatBlockEyebrow: View {
    let symbol: String
    let label: String

    var body: some View {
        HStack(spacing: DS.Spacing.xs + 2) {
            Image(systemName: symbol)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(DS.Palette.inkSecondary)
                .accessibilityHidden(true)
            Text(label)
                .font(DS.Typography.caption.weight(.semibold))
                .foregroundStyle(DS.Palette.inkSecondary)
                .tracking(DS.Tracking.label)
        }
    }
}

/// A block whose entity is not in the loaded list, or a store that is still fetching it. No dead
/// affordance either way: the card says what it cannot do.
struct ChatBlockNotice: View {
    let symbol: String
    let label: String
    let message: String
    var isLoading = false
    var identifier: String

    var body: some View {
        ChatBlockCard {
            VStack(alignment: .leading, spacing: DS.Spacing.xs + 2) {
                ChatBlockEyebrow(symbol: symbol, label: label)
                HStack(spacing: DS.Spacing.sm) {
                    if isLoading {
                        ProgressView().controlSize(.mini).tint(DS.Palette.inkSecondary)
                    }
                    Text(message)
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(identifier)
    }
}

/// Summary plus its one destination, shared by the goal, memory and conversation cards. The
/// action is the card's only affordance, so it is drawn as the compact button it is
/// (Flutter `ChatBlockLinkCard`).
struct ChatBlockLinkCard: View {
    let block: ChatBlock
    let symbol: String
    let eyebrow: String
    let summary: String
    let action: String
    var footer: (() -> AnyView)?
    var onOpen: (() -> Void)?

    var body: some View {
        ChatBlockCard {
            VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                ChatBlockEyebrow(symbol: symbol, label: eyebrow)
                if !summary.isEmpty {
                    Text(summary)
                        .font(DS.Typography.callout)
                        .foregroundStyle(DS.Palette.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let footer { footer() }
                if let onOpen {
                    ChatBlockAction(title: action, identifier: "\(identifier).open", action: onOpen)
                }
            }
        }
        .accessibilityIdentifier(identifier)
    }

    var identifier: String {
        "chat.block-link.\(block.id)"
    }
}

/// A left-aligned compact button inside a card (Flutter `OmiButton.tertiary` with `open_in_new`).
struct ChatBlockAction: View {
    let title: String
    let identifier: String
    let action: () -> Void

    var body: some View {
        Button {
            DSHaptics.tap()
            action()
        } label: {
            HStack(spacing: DS.Spacing.xs + 2) {
                Image(systemName: "arrow.up.forward.app").font(.system(size: 12, weight: .semibold))
                Text(title).font(DS.Typography.caption.weight(.semibold))
            }
            .foregroundStyle(DS.Palette.agent)
            .padding(.horizontal, DS.Spacing.md)
            .padding(.vertical, DS.Spacing.xs + 2)
            .frame(minHeight: 36)
            .background(DS.Palette.agentSoft, in: Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(identifier)
    }
}
