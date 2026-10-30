import SwiftUI

/// Liquid Glass on iOS 26, material below. Same approach as Persona's `personaGlass`.
public extension View {
    @ViewBuilder
    func omiGlass(in shape: some Shape, interactive: Bool = false, tint: Color? = nil) -> some View {
        if #available(iOS 26.0, macOS 26.0, *) {
            glassEffect(.regular.tint(tint).interactive(interactive), in: shape)
        } else {
            background(.regularMaterial, in: shape)
                .overlay { if let tint { shape.fill(tint.opacity(0.18)) } }
        }
    }

    /// Standard content card: solid surface, continuous corners, a thin outline in both modes.
    func omiCard(padding: CGFloat = DS.Spacing.lg) -> some View {
        self.padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .omiCardSurface()
    }

    /// Rows grouped on one card (Home's For you, a day's conversations): side padding only, the
    /// rows bring their own height and hairlines.
    func omiGroup() -> some View {
        self.padding(.horizontal, DS.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .omiCardSurface()
    }

    /// Just the card surface (fill and outline), for rows that set their own padding and frame.
    func omiCardSurface(radius: CGFloat = DS.Radius.card) -> some View {
        background(DS.Palette.card, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .strokeBorder(DS.Palette.cardStroke, lineWidth: 1)
            }
    }

    /// A system `List` in Omi's look: the page behind it, not the grouped gray.
    func omiList() -> some View {
        scrollContentBackground(.hidden).background(DS.Palette.background)
    }

    /// A row of a system `List` on Omi's quiet surface with a hairline separator.
    func omiListRow() -> some View {
        listRowBackground(DS.Palette.card).listRowSeparatorTint(DS.Palette.hairline)
    }

    /// No iOS 26 scroll edge blur: under Omi's own header it shows as a lighter band across the page.
    @ViewBuilder
    func omiNoScrollEdgeEffect() -> some View {
        if #available(iOS 26.0, macOS 26.0, *) {
            scrollEdgeEffectHidden(true, for: .top)
        } else {
            self
        }
    }

    /// The small round header button (avatar, device).
    func omiHeaderCircle() -> some View {
        frame(width: DS.Size.headerButton, height: DS.Size.headerButton)
            .omiGlass(in: Circle(), interactive: true)
    }
}
