import SwiftUI

/// Recording view showing recording status, audio levels, and live transcript
struct RecordingView: View {
    @ObservedObject var appState: AppState
    @ObservedObject private var liveTranscript = LiveTranscriptMonitor.shared

    @State private var showNameSpeakerSheet = false
    @State private var selectedSpeakerSegment: SpeakerSegment? = nil

    /// Compute speaker names from the live speaker-person map
    private var speakerNames: [Int: String] {
        var names: [Int: String] = [:]
        for (speakerId, personId) in appState.liveSpeakerPersonMap {
            if let person = appState.peopleById[personId] {
                names[speakerId] = person.name
            }
        }
        return names
    }

    var body: some View {
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
                LiveTranscriptView(
                    segments: liveTranscript.segments,
                    speakerNames: speakerNames,
                    onSpeakerTapped: { segment in
                        selectedSpeakerSegment = segment
                        showNameSpeakerSheet = true
                    }
                )
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task {
            await appState.fetchPeople()
        }
        .dismissableSheet(isPresented: $showNameSpeakerSheet) {
            if let segment = selectedSpeakerSegment {
                LiveNameSpeakerSheet(
                    speakerId: segment.speaker,
                    sampleText: segment.text,
                    people: appState.people,
                    currentPersonId: appState.liveSpeakerPersonMap[segment.speaker],
                    onSave: { personId in
                        appState.liveSpeakerPersonMap[segment.speaker] = personId
                        showNameSpeakerSheet = false
                    },
                    onCreatePerson: { name in
                        return await appState.createPerson(name: name)
                    },
                    onDismiss: {
                        showNameSpeakerSheet = false
                    }
                )
            }
        }
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

#Preview {
    RecordingView(appState: AppState())
        .frame(width: 500, height: 600)
        .background(OmiColors.backgroundSecondary)
}
