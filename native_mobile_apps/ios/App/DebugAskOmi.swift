#if DEBUG
    import AVFoundation
    import Foundation
    import OmiAudio
    import OmiService

    /// Simulator QA of "Press once to ask Omi" without an Omi (`-omiAskAudioFile`, with
    /// `-omiFakeDevice connected`): once the press-once lesson is up (or right away with
    /// `-omiAskNow YES`), presses the button, plays the file as the Omi's audio in real time and
    /// presses again if the question has not ended by itself. Debug builds only.
    @MainActor
    enum DebugAskOmi {
        static func start(askOmi: AskOmiStore, tutorial: ButtonTutorialStore) {
            guard let file = DebugLaunchOptions.current.askAudioFile else { return }
            let now = DebugLaunchOptions.current.asksNow
            Task { @MainActor in
                while !now, tutorial.lesson != .ask {
                    try? await Task.sleep(for: .milliseconds(300))
                }
                try? await Task.sleep(for: .seconds(2.5))
                askOmi.handle(.askToggle)
                guard askOmi.isListening else { return }
                let capture = AudioFileCapture(url: file)
                guard let audio = try? capture.start().pcm16 else { return }
                let feed = Task { @MainActor in
                    for await chunk in audio {
                        askOmi.ingest(pcm16: chunk)
                    }
                }
                let seconds = (try? AVAudioFile(forReading: file)).map { Double($0.length) / $0.processingFormat.sampleRate } ?? 5
                // The file, then the quiet room (pause) that ends the question by itself.
                try? await Task.sleep(for: .seconds(seconds + 4))
                if askOmi.isListening { askOmi.handle(.askToggle) }
                feed.cancel()
                capture.stop()
            }
        }
    }
#endif
