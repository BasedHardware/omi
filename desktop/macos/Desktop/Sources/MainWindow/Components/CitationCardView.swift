import SwiftUI
import OmiTheme

/// A tappable card displaying a citation source (conversation or memory)
struct CitationCardView: View {
    let citation: Citation
    let onTap: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: OmiSpacing.sm) {
                // Emoji or icon
                Text(citation.emoji ?? "📝")
                    .scaledFont(size: OmiType.subheading)
                    .frame(width: 24, height: 24)

                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                    // Title
                    Text(citation.title)
                        .scaledFont(size: OmiType.caption, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                        .lineLimit(1)

                    // Preview
                    Text(citation.preview)
                        .scaledFont(size: OmiType.caption)
                        .foregroundColor(OmiColors.textSecondary)
                        .lineLimit(1)
                }

                Spacer()

                // Chevron
                Image(systemName: "chevron.right")
                    .scaledFont(size: OmiType.micro, weight: .medium)
                    .foregroundColor(OmiColors.textTertiary)
            }
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
            .background(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                    .fill(isHovering ? OmiColors.backgroundTertiary : OmiColors.backgroundSecondary)
            )
            .overlay(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                    .stroke(OmiColors.backgroundTertiary, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
    }
}

/// A view that displays a list of citation cards
struct CitationCardsView: View {
    let citations: [Citation]
    let onCitationTap: (Citation) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: OmiSpacing.xs) {
            // Section header
            HStack(spacing: OmiSpacing.xxs) {
                Image(systemName: "quote.opening")
                    .scaledFont(size: OmiType.micro)
                    .foregroundColor(OmiColors.textTertiary)
                Text("Sources")
                    .scaledFont(size: OmiType.caption, weight: .medium)
                    .foregroundColor(OmiColors.textTertiary)
            }
            .padding(.top, OmiSpacing.xxs)

            // Citation cards
            ForEach(citations) { citation in
                CitationCardView(citation: citation) {
                    onCitationTap(citation)
                }
            }
        }
    }
}
