import SwiftUI

/// A tappable card displaying a citation source (conversation or memory)
struct CitationCardView: View {
    let citation: Citation
    let onTap: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 10) {
                // Emoji or icon
                Text(citation.emoji ?? "📝")
                    .scaledFont(size: 16)
                    .frame(width: 24, height: 24)

                VStack(alignment: .leading, spacing: 2) {
                    // Title
                    Text(citation.title)
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                        .lineLimit(1)

                    // Preview
                    Text(citation.preview)
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textSecondary)
                        .lineLimit(1)
                }

                Spacer()

                // Chevron
                Image(systemName: "chevron.right")
                    .scaledFont(size: 10, weight: .medium)
                    .foregroundColor(OmiColors.textTertiary)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isHovering ? OmiColors.backgroundTertiary : OmiColors.backgroundSecondary)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
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
        VStack(alignment: .leading, spacing: 6) {
            // Section header
            HStack(spacing: 4) {
                Image(systemName: "quote.opening")
                    .scaledFont(size: 10)
                    .foregroundColor(OmiColors.textTertiary)
                Text("Sources")
                    .scaledFont(size: 11, weight: .medium)
                    .foregroundColor(OmiColors.textTertiary)
            }
            .padding(.top, 4)

            // Citation cards
            ForEach(citations) { citation in
                CitationCardView(citation: citation) {
                    onCitationTap(citation)
                }
            }
        }
    }
}
