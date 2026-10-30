import AVFoundation
import Observation
import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// The recording at the top of the transcript: play/pause, scrub, speed, share.
struct AudioPlayerBar: View {
    let store: ConversationDetailStore
    let onShare: () -> Void
    @State private var playback = AudioPlayback()
    @State private var scrubbing: Double?

    var body: some View {
        HStack(spacing: DS.Spacing.md) {
            switch store.audio {
            case .idle, .preparing:
                ProgressView().controlSize(.small)
                Text(L("nativeAudioPreparing")).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
                Spacer(minLength: 0)
            case .unavailable:
                Image(systemName: "waveform.slash").foregroundStyle(DS.Palette.inkTertiary)
                Text(L("nativeAudioUnavailable")).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
                Spacer(minLength: 0)
            case let .ready(url, duration):
                controls
                    .task(id: url) { playback.load(url, duration: duration) }
            }
        }
        .padding(.horizontal, DS.Spacing.md)
        .frame(minHeight: 52)
        .omiCard(padding: DS.Spacing.xs)
        .task { await store.loadAudio() }
        .onDisappear { playback.stop() }
    }

    private var controls: some View {
        HStack(spacing: DS.Spacing.sm) {
            Button {
                DSHaptics.tap()
                if playback.isPlaying { playback.pause() } else { playback.play() }
            } label: {
                Image(systemName: playback.isPlaying ? "pause.fill" : "play.fill")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(DS.Palette.onAccent)
                    .frame(width: 36, height: 36)
                    .background(DS.Palette.accent, in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(playback.isPlaying ? L("nativePause") : L("nativePlay"))
            Slider(
                value: Binding(get: { scrubbing ?? playback.position }, set: { scrubbing = $0 }),
                in: 0 ... max(playback.duration, 1)
            ) { editing in
                if !editing, let value = scrubbing {
                    playback.seek(to: value)
                    scrubbing = nil
                }
            }
            .tint(DS.Palette.agent)
            .accessibilityLabel(L("nativePlaybackPosition"))
            Text(Self.time(scrubbing ?? playback.position))
                .font(DS.Typography.micro)
                .monospacedDigit()
                .foregroundStyle(DS.Palette.inkSecondary)
                .frame(minWidth: 36, alignment: .trailing)
            Menu {
                ForEach([0.75, 1, 1.25, 1.5, 2] as [Float], id: \.self) { rate in
                    Button { playback.rate = rate } label: {
                        if playback.rate == rate { Label(Self.rate(rate), systemImage: "checkmark") } else { Text(Self.rate(rate)) }
                    }
                }
            } label: {
                Text(Self.rate(playback.rate))
                    .font(DS.Typography.micro)
                    .foregroundStyle(DS.Palette.ink)
                    .padding(.horizontal, DS.Spacing.sm)
                    .padding(.vertical, DS.Spacing.xs)
                    .background(DS.Palette.cardRaised, in: Capsule())
            }
            .accessibilityLabel(L("nativePlaybackSpeed"))
            Button(action: onShare) { Image(systemName: "square.and.arrow.up").foregroundStyle(DS.Palette.inkSecondary) }
                .buttonStyle(.plain)
                .accessibilityLabel(L("shareAudio"))
        }
    }

    static func time(_ seconds: Double) -> String {
        let total = Int(seconds.rounded(.down))
        return String(format: "%d:%02d", total / 60, total % 60)
    }

    static func rate(_ rate: Float) -> String {
        rate == rate.rounded() ? "\(Int(rate))×" : "\(rate.formatted(.number.precision(.fractionLength(0 ... 2))))×"
    }
}

/// AVPlayer for one signed URL, publishing position and play state.
@MainActor
@Observable
final class AudioPlayback {
    private(set) var isPlaying = false
    private(set) var position: Double = 0
    private(set) var duration: Double = 0
    var rate: Float = 1 {
        didSet { if isPlaying { player?.rate = rate } }
    }

    @ObservationIgnored private var player: AVPlayer?
    @ObservationIgnored private var observer: Any?
    @ObservationIgnored private var loadedURL: URL?
    @ObservationIgnored private var endObserver: NSObjectProtocol?

    func load(_ url: URL, duration: TimeInterval?) {
        guard url != loadedURL else { return }
        loadedURL = url
        self.duration = duration ?? 0
        let item = AVPlayerItem(url: url)
        let player = AVPlayer(playerItem: item)
        self.player = player
        let interval = CMTime(seconds: 0.25, preferredTimescale: 600)
        observer = player.addPeriodicTimeObserver(forInterval: interval, queue: .main) { [weak self] time in
            MainActor.assumeIsolated {
                guard let self else { return }
                self.position = time.seconds.isFinite ? time.seconds : 0
                if let seconds = self.player?.currentItem?.duration.seconds, seconds.isFinite, seconds > 0 { self.duration = seconds }
            }
        }
        endObserver = NotificationCenter.default.addObserver(
            forName: AVPlayerItem.didPlayToEndTimeNotification, object: item, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated {
                self?.isPlaying = false
                self?.player?.seek(to: .zero)
            }
        }
    }

    func play() {
        #if os(iOS)
            // A live capture owns the session (play-and-record); playback joins it instead.
            let session = AVAudioSession.sharedInstance()
            if session.category != .playAndRecord, session.category != .record {
                try? session.setCategory(.playback, mode: .spokenAudio)
                try? session.setActive(true)
            }
        #endif
        player?.playImmediately(atRate: rate)
        isPlaying = player != nil
    }

    func pause() {
        player?.pause()
        isPlaying = false
    }

    /// Releases the player (the transcript tab closed); `load` starts over.
    func stop() {
        pause()
        if let observer { player?.removeTimeObserver(observer) }
        if let endObserver { NotificationCenter.default.removeObserver(endObserver) }
        observer = nil
        endObserver = nil
        player = nil
        loadedURL = nil
    }

    func seek(to seconds: Double) {
        position = seconds
        player?.seek(to: CMTime(seconds: seconds, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
    }
}
