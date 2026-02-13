import SwiftUI

/// Detailed transcript view showing all segments as chat bubbles
struct TranscriptDetailView: View {
    let segments: [TranscriptSegment]

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(segments) { segment in
                    SpeakerBubbleView(
                        segment: segment,
                        isUser: segment.isUser
                    )
                }
            }
            .padding(16)
        }
    }
}

#Preview {
    TranscriptDetailView(segments: [])
        .frame(width: 400, height: 400)
        .background(OmiColors.backgroundSecondary)
}
