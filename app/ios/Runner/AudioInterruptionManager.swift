import Foundation
import AVFoundation
import Flutter

// Forwards AVAudioSession interruption events to Dart via a FlutterEventChannel.
//
// Context: issue #6499. When an incoming phone call interrupts the audio
// session during phone-mic recording, iOS pauses the underlying AVAudioEngine
// (inside flutter_sound) and never resumes it on its own. Without this bridge
// there is no Dart-side signal that capture has stopped, so the UI keeps
// showing "recording" and the transcript is silently truncated.
//
// On `.began`, we forward a {"type": "began"} event. On `.ended`, we
// reactivate the shared AVAudioSession — a prerequisite for flutter_sound to
// successfully re-open the recorder on the Dart side — and then forward a
// {"type": "ended"} event. The Dart side is responsible for restarting the
// actual recording pipeline (see CaptureProvider._onAudioInterruptionEnded).
class AudioInterruptionManager: NSObject, FlutterStreamHandler {
    private var eventSink: FlutterEventSink?

    func register(with messenger: FlutterBinaryMessenger) {
        let channel = FlutterEventChannel(
            name: "com.omi.ios/audioInterruption",
            binaryMessenger: messenger
        )
        channel.setStreamHandler(self)
    }

    // MARK: FlutterStreamHandler

    func onListen(withArguments arguments: Any?, eventSink events: @escaping FlutterEventSink) -> FlutterError? {
        self.eventSink = events
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleInterruption(_:)),
            name: AVAudioSession.interruptionNotification,
            object: nil
        )
        return nil
    }

    func onCancel(withArguments arguments: Any?) -> FlutterError? {
        NotificationCenter.default.removeObserver(self, name: AVAudioSession.interruptionNotification, object: nil)
        self.eventSink = nil
        return nil
    }

    // MARK: Interruption handling

    @objc private func handleInterruption(_ notification: Notification) {
        guard
            let userInfo = notification.userInfo,
            let rawType = userInfo[AVAudioSessionInterruptionTypeKey] as? UInt,
            let type = AVAudioSession.InterruptionType(rawValue: rawType)
        else {
            return
        }

        switch type {
        case .began:
            emit(["type": "began"])
        case .ended:
            // iOS requires us to explicitly reactivate the session before any
            // AVAudioEngine-based capture (including flutter_sound) can resume.
            // Even if this fails we still forward `ended` so Dart can attempt
            // recovery and surface the failure through the stall heartbeat.
            do {
                try AVAudioSession.sharedInstance().setActive(true)
            } catch {
                NSLog("[AudioInterruptionManager] setActive(true) after .ended failed: \(error.localizedDescription)")
            }

            var payload: [String: Any] = ["type": "ended"]
            if let rawOptions = userInfo[AVAudioSessionInterruptionOptionKey] as? UInt {
                let options = AVAudioSession.InterruptionOptions(rawValue: rawOptions)
                payload["shouldResume"] = options.contains(.shouldResume)
            }
            emit(payload)
        @unknown default:
            return
        }
    }

    private func emit(_ payload: [String: Any]) {
        DispatchQueue.main.async { [weak self] in
            self?.eventSink?(payload)
        }
    }
}
