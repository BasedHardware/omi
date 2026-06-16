import SwiftUI

/// Detailed transcript view showing all segments as chat bubbles
struct TranscriptDetailView: View {
    let segments: [TranscriptSegment]
    var peopleById: [String: Person] = [:]
    var onSpeakerTapped: ((TranscriptSegment) -> Void)? = nil

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(segments) { segment in
                    SpeakerBubbleView(
                        segment: segment,
                        isUser: segment.isUser,
                        personName: segment.personId.flatMap { peopleById[$0]?.name },
                        onSpeakerTapped: segment.isUser ? nil : (onSpeakerTapped != nil ? { onSpeakerTapped?(segment) } : nil)
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
