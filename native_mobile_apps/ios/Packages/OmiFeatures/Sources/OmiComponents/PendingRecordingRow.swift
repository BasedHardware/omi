import OmiDesign
import OmiService
import SwiftUI
#if canImport(UIKit)
    import UIKit
#endif

/// A recording still on the phone (from the Omi or the phone's microphone): when and how long,
/// play it, share it as a WAV, or process it now (Flutter `sync_page`, `recording_detail_sheet`).
public struct PendingRecordingRow: View {
    @Environment(SyncStore.self) private var sync
    let recording: PendingRecording
    let player: AudioClipPlayer
    @State private var shared: SharedFile?
    @State private var unavailable = false

    public init(recording: PendingRecording, player: AudioClipPlayer) {
        self.recording = recording
        self.player = player
    }

    public var body: some View {
        HStack(spacing: DS.Spacing.md) {
            Button {
                Task {
                    let ok = await player.toggle(recording.filename) { await decoded().flatMap { try? Data(contentsOf: $0) } }
                    unavailable = !ok
                }
            } label: {
                Image(systemName: player.playingID == recording.filename ? "stop.circle.fill" : "play.circle.fill")
                    .font(.title2)
                    .foregroundStyle(DS.Palette.ink)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(player.playingID == recording.filename ? L("nativeRecordingStop") : L("play"))
            VStack(alignment: .leading, spacing: 2) {
                Text(Date(timeIntervalSince1970: recording.startedAt).formatted(date: .abbreviated, time: .shortened))
                Text(Duration.seconds(recording.seconds.rounded()).formatted(.units(allowed: [.hours, .minutes, .seconds])))
                    .font(DS.Typography.caption)
                    .foregroundStyle(DS.Palette.inkSecondary)
            }
            Spacer()
            if recording.jobID != nil {
                Text(L("nativeRecordingProcessing")).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkTertiary)
            } else {
                Menu {
                    Button(L("nativeRecordingProcessNow"), systemImage: "arrow.up.circle") {
                        Task { await sync.process(recording.filename) }
                    }
                    Button(L("share"), systemImage: "square.and.arrow.up") {
                        Task {
                            if let url = await decoded() { shared = SharedFile(url: url) } else { unavailable = true }
                        }
                    }
                    Button(L("delete"), systemImage: "trash", role: .destructive) { sync.delete(recording.filename) }
                } label: {
                    Image(systemName: "ellipsis.circle").font(.title3).foregroundStyle(DS.Palette.inkSecondary)
                }
                .accessibilityLabel(L("moreOptions"))
                .accessibilityIdentifier("recording.menu")
            }
        }
        .alert(L("nativeRecordingUnavailable"), isPresented: $unavailable) { Button(L("ok"), role: .cancel) {} }
        #if canImport(UIKit)
            .sheet(item: $shared) { file in FileShareSheet(url: file.url).presentationDetents([.medium, .large]) }
        #endif
    }

    /// Decoded on demand into a temporary WAV (recordings are at most five minutes).
    private func decoded() async -> URL? {
        await Task.yield()
        return sync.audioFile(for: recording.filename)
    }
}

private struct SharedFile: Identifiable {
    let id = UUID()
    let url: URL
}

#if canImport(UIKit)
    private struct FileShareSheet: UIViewControllerRepresentable {
        let url: URL

        func makeUIViewController(context _: Context) -> UIActivityViewController {
            UIActivityViewController(activityItems: [url], applicationActivities: nil)
        }

        func updateUIViewController(_: UIActivityViewController, context _: Context) {}
    }
#endif
