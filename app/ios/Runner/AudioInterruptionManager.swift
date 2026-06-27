import Foundation
import AVFoundation
import CallKit
import Flutter

// Detects phone calls via CXCallObserver and forwards began/ended events to
// Dart over a FlutterEventChannel (com.omi.ios/audioInterruption).
//
// Context: issue #6499. When a phone call arrives during phone-mic recording,
// flutter_sound's AVAudioEngine may silently stop delivering audio without the
// app receiving an AVAudioSession.interruptionNotification (e.g. when the
// session category is configured by flutter_sound in a way that prevents
// standard interruption callbacks on certain iOS versions).
//
// CXCallObserver fires for every call regardless of audio session config, so
// it is used as the primary signal instead of interruptionNotification.
//
// On call start  → emit {"type": "began"}
// On all calls ended → reactivate AVAudioSession + emit {"type": "ended", "shouldResume": true}
// Dart side restarts recording in CaptureProvider._onAudioInterruptionEnded.
class AudioInterruptionManager: NSObject, FlutterStreamHandler, CXCallObserverDelegate {
    private var eventSink: FlutterEventSink?
    private let callObserver = CXCallObserver()
    private var wasInterrupted = false
    // Must be stored as a property — a local FlutterEventChannel is deallocated
    // immediately, causing MissingPluginException when Dart calls listen.
    private var eventChannel: FlutterEventChannel?

    func register(with messenger: FlutterBinaryMessenger) {
        eventChannel = FlutterEventChannel(
            name: "com.omi.ios/audioInterruption",
            binaryMessenger: messenger
        )
        eventChannel?.setStreamHandler(self)
    }

    // MARK: FlutterStreamHandler

    func onListen(withArguments arguments: Any?, eventSink events: @escaping FlutterEventSink) -> FlutterError? {
        self.eventSink = events
        callObserver.setDelegate(self, queue: DispatchQueue.main)
        NSLog("[AudioInterruptionManager] Dart listening — CXCallObserver active")
        return nil
    }

    func onCancel(withArguments arguments: Any?) -> FlutterError? {
        callObserver.setDelegate(nil, queue: nil)
        self.eventSink = nil
        wasInterrupted = false
        return nil
    }

    // MARK: CXCallObserverDelegate

    func callObserver(_ callObserver: CXCallObserver, callChanged call: CXCall) {
        let activeCalls = callObserver.calls.filter { !$0.hasEnded }
        NSLog("[AudioInterruptionManager] callChanged uuid=\(call.uuid) hasEnded=\(call.hasEnded) isOutgoing=\(call.isOutgoing) activeCalls=\(activeCalls.count) wasInterrupted=\(wasInterrupted)")

        if activeCalls.isEmpty {
            guard wasInterrupted else { return }
            wasInterrupted = false
            NSLog("[AudioInterruptionManager] all calls ended — reactivating session + emitting ended")
            do {
                try AVAudioSession.sharedInstance().setActive(true)
            } catch {
                NSLog("[AudioInterruptionManager] setActive(true) after call ended failed: \(error.localizedDescription)")
            }
            emit(["type": "ended", "shouldResume": true])
        } else if !wasInterrupted {
            wasInterrupted = true
            NSLog("[AudioInterruptionManager] call became active — emitting began")
            emit(["type": "began"])
        }
    }

    // MARK: Private

    private func emit(_ payload: [String: Any]) {
        DispatchQueue.main.async { [weak self] in
            self?.eventSink?(payload)
        }
    }
}
