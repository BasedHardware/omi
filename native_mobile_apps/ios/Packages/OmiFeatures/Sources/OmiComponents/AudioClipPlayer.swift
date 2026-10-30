import AVFoundation
import Observation

/// Plays one short voice clip at a time: WAV bytes the backend sent (speaker prompts, earlier
/// voice matches) or a signed sample URL (a person's voice samples; no auth headers needed).
@MainActor
@Observable
public final class AudioClipPlayer: NSObject, AVAudioPlayerDelegate {
    /// What is playing now, by the caller's id.
    public private(set) var playingID: String?
    /// The clip the caller is waiting for (download in flight).
    public private(set) var loadingID: String?
    @ObservationIgnored private var player: AVAudioPlayer?
    @ObservationIgnored private var streamer: AVPlayer?
    @ObservationIgnored private var endObserver: NSObjectProtocol?

    override public init() {}

    /// Starts `id`, or stops it when it is already playing. `load` fetches the WAV; `false` when nothing could play.
    @discardableResult
    public func toggle(_ id: String, load: () async -> Data?) async -> Bool {
        if playingID == id || loadingID == id {
            stop()
            return true
        }
        stop()
        loadingID = id
        let data = await load()
        guard loadingID == id else { return true }
        loadingID = nil
        guard let data, let player = try? AVAudioPlayer(data: data) else { return false }
        activateSession()
        player.delegate = self
        self.player = player
        playingID = player.play() ? id : nil
        return playingID != nil
    }

    /// Streams a remote clip, or stops it when it is already playing.
    public func toggle(_ id: String, url: URL) {
        if playingID == id {
            stop()
            return
        }
        stop()
        activateSession()
        let item = AVPlayerItem(url: url)
        let streamer = AVPlayer(playerItem: item)
        endObserver = NotificationCenter.default.addObserver(
            forName: AVPlayerItem.didPlayToEndTimeNotification, object: item, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.stop() }
        }
        self.streamer = streamer
        streamer.play()
        playingID = id
    }

    public func stop() {
        player?.stop()
        player = nil
        streamer?.pause()
        streamer = nil
        if let endObserver { NotificationCenter.default.removeObserver(endObserver) }
        endObserver = nil
        playingID = nil
        loadingID = nil
    }

    public nonisolated func audioPlayerDidFinishPlaying(_: AVAudioPlayer, successfully _: Bool) {
        Task { @MainActor in self.stop() }
    }

    private func activateSession() {
        #if os(iOS)
            // A running capture owns the session (play-and-record); it plays clips as is.
            let session = AVAudioSession.sharedInstance()
            guard session.category != .playAndRecord, session.category != .record else { return }
            try? session.setCategory(.playback, mode: .spokenAudio)
            try? session.setActive(true)
        #endif
    }
}
