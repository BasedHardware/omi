import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// The pieces the thread is drawn with, as in Messages: the bubble's shape (smaller corners on the
/// sender's side inside a group, a quiet tail on its last bubble), Omi's avatar, the widest a
/// bubble may get, and a stack for cards of one kind.

extension EnvironmentValues {
    /// The widest a bubble gets: about 78 % of the thread's width (set by the chat).
    @Entry var chatBubbleWidth: CGFloat = 300
}

/// Where a bubble sits in its group, which side it is on.
struct ChatBubbleShape: Shape {
    let isUser: Bool
    let position: ChatGrouping.Position

    func path(in rect: CGRect) -> Path {
        let round = DS.Radius.bubble
        let top = position.isFirst ? round : DS.Radius.bubbleJoined
        let bottom = position.isLast ? DS.Radius.bubbleTail : DS.Radius.bubbleJoined
        let radii = isUser
            ? RectangleCornerRadii(topLeading: round, bottomLeading: round, bottomTrailing: bottom, topTrailing: top)
            : RectangleCornerRadii(topLeading: top, bottomLeading: bottom, bottomTrailing: round, topTrailing: round)
        return UnevenRoundedRectangle(cornerRadii: radii, style: .continuous).path(in: rect)
    }
}

extension View {
    /// A chat bubble's padding, fill and shape (also the long-press preview's outline).
    func chatBubble(_ color: Color, isUser: Bool, position: ChatGrouping.Position) -> some View {
        let shape = ChatBubbleShape(isUser: isUser, position: position)
        return padding(.horizontal, 14)
            .padding(.vertical, 9)
            .background(color, in: shape)
            .contentShape(.contextMenuPreview, shape)
            .contentShape(shape)
    }

    /// In Omi's column: clear of the avatar beside its bubbles.
    func omiColumn() -> some View {
        padding(.leading, OmiAvatar.column)
    }
}

/// Omi's picture beside the last bubble of an Omi group (the pendant); an empty slot of the same
/// width beside the others, so all of Omi's bubbles line up.
struct OmiAvatar: View {
    let shows: Bool

    /// The avatar and the gap after it.
    static let column = DS.Size.chatAvatar + 6

    var body: some View {
        Group {
            if shows {
                OmiPendantThumbnail(size: DS.Size.chatAvatar)
                    .transition(.opacity)
            } else {
                Color.clear
            }
        }
        .frame(width: DS.Size.chatAvatar, height: DS.Size.chatAvatar)
        .accessibilityHidden(true)
    }
}

/// Cards of one kind in a row: the first, and "2 more" that opens the rest.
struct ChatCardStack<Item: Identifiable, Card: View>: View {
    let items: [Item]
    @ViewBuilder let card: (Item) -> Card
    @State private var isOpen = false

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.xs + 2) {
            ForEach(isOpen ? items : Array(items.prefix(1))) { item in
                card(item).transition(.opacity.combined(with: .move(edge: .top)))
            }
            if items.count > 1, !isOpen {
                Button {
                    DSHaptics.selection()
                    withAnimation(DS.Motion.snappy) { isOpen = true }
                } label: {
                    HStack(spacing: DS.Spacing.xs) {
                        Text(L("nativeChatMoreCards", String(items.count - 1)))
                        Image(systemName: "chevron.down").imageScale(.small)
                    }
                    .font(DS.Typography.caption.weight(.medium))
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .padding(.horizontal, DS.Spacing.xs)
                    .frame(minHeight: 28)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("chat.cardStack.more")
            }
        }
    }
}
