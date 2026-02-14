import SwiftUI

/// Recording view with split panel for transcript (left) and notes (right)
struct RecordingViewWithNotes: View {
    @ObservedObject var appState: AppState
    @ObservedObject private var liveTranscript = LiveTranscriptMonitor.shared
    @ObservedObject private var liveNotes = LiveNotesMonitor.shared

    /// Persisted panel width ratio (0.0-1.0, representing transcript panel width)
    @AppStorage("recordingNotesPanelRatio") private var panelRatio: Double = 0.65

    /// Minimum panel width
    private let minPanelWidth: CGFloat = 200

    /// Whether notes panel is visible
    @State private var isNotesPanelVisible: Bool = true

    var body: some View {
        GeometryReader { geometry in
            let totalWidth = geometry.size.width
            let transcriptWidth = isNotesPanelVisible
                ? max(minPanelWidth, totalWidth * panelRatio)
                : totalWidth
            let notesWidth = isNotesPanelVisible
                ? max(minPanelWidth, totalWidth - transcriptWidth - 1) // -1 for divider
                : 0

            HStack(spacing: 0) {
                // Left panel: Transcript
                transcriptPanel
                    .frame(width: transcriptWidth)

                if isNotesPanelVisible {
                    // Draggable divider
                    DraggableDivider(
                        panelRatio: $panelRatio,
                        totalWidth: totalWidth,
                        minRatio: minPanelWidth / totalWidth,
                        maxRatio: 1.0 - (minPanelWidth / totalWidth)
                    )

                    // Right panel: Notes
                    LiveNotesView()
                        .frame(width: notesWidth)
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button(action: { withAnimation { isNotesPanelVisible.toggle() } }) {
                    Image(systemName: isNotesPanelVisible ? "sidebar.right" : "sidebar.right")
                        .foregroundColor(isNotesPanelVisible ? OmiColors.purplePrimary : OmiColors.textTertiary)
                }
                .help(isNotesPanelVisible ? "Hide notes panel" : "Show notes panel")
            }
        }
    }

    // MARK: - Transcript Panel

    private var transcriptPanel: some View {
        VStack(spacing: 0) {
            // Recording header with status and audio levels
            RecordingHeaderView(appState: appState)
                .padding(16)

            Divider()
                .background(OmiColors.backgroundTertiary)

            // Live transcript
            if liveTranscript.isEmpty {
                emptyTranscriptView
            } else {
                LiveTranscriptView(segments: liveTranscript.segments)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(OmiColors.backgroundPrimary)
    }

    private var emptyTranscriptView: some View {
        VStack(spacing: 16) {
            Image(systemName: "waveform")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.textTertiary)
                .opacity(0.5)

            Text("Listening...")
                .scaledFont(size: 16, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)

            Text("Start speaking and your transcript will appear here")
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(32)
    }
}

// MARK: - Draggable Divider

private struct DraggableDivider: View {
    @Binding var panelRatio: Double
    let totalWidth: CGFloat
    let minRatio: Double
    let maxRatio: Double

    @State private var isDragging = false

    var body: some View {
        Rectangle()
            .fill(isDragging ? OmiColors.purplePrimary : OmiColors.border)
            .frame(width: 1)
            .contentShape(Rectangle().inset(by: -4)) // Larger hit area
            .onHover { hovering in
                if hovering {
                    NSCursor.resizeLeftRight.push()
                } else {
                    NSCursor.pop()
                }
            }
            .gesture(
                DragGesture()
                    .onChanged { value in
                        isDragging = true
                        let newRatio = Double(value.location.x / totalWidth)
                        panelRatio = min(maxRatio, max(minRatio, newRatio))
                    }
                    .onEnded { _ in
                        isDragging = false
                    }
            )
    }
}

// MARK: - Preview

#Preview {
    RecordingViewWithNotes(appState: AppState())
        .frame(width: 900, height: 600)
        .background(OmiColors.backgroundPrimary)
}
