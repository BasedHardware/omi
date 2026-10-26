import Foundation
import SwiftUI

/// Simulator-only fixture. The production view and recorder policy compile
/// unchanged; permission and audio-session I/O never touch a microphone.
@MainActor
private func verifyRecorderLifecycle() throws {
    enum ExpectedFailure: Error { case activation }
    UserDefaults.standard.set("watch-controls-fixture", forKey: "omiOwnerUID")
    var permissions: [(Bool) -> Void] = []
    var activations = 0
    var deactivations = 0
    let recorder = WatchAudioRecorderViewModel(
        permissionRequest: { permissions.append($0) },
        activateSession: { activations += 1; throw ExpectedFailure.activation },
        deactivateSession: { deactivations += 1 }
    )

    recorder.startRecording()
    precondition(permissions.count == 1)
    recorder.stopRecording()
    permissions.removeFirst()(true)
    precondition(!recorder.isRecording && activations == 0 && deactivations == 1,
                 "a cancelled permission request must not activate the microphone")

    recorder.startRecording()
    recorder.stopRecording()
    recorder.startRecording()
    permissions.removeFirst()(true)
    precondition(activations == 0, "an old permission answer must not adopt a newer start")
    permissions.removeFirst()(true)
    precondition(activations == 1 && deactivations == 3 && !recorder.isRecording,
                 "failed startup must release its audio session")

    recorder.isRecording = true
    recorder.stopRecording()
    precondition(!recorder.isRecording && recorder.recordingStartedAt == nil && deactivations == 4,
                 "Stop must end recorder state and release microphone ownership")
    recorder.stopRecording()
    precondition(!recorder.isRecording && deactivations == 5, "repeated Stop must remain safe")

    recorder.startRecording()
    permissions.removeFirst()(false)
    precondition(!recorder.isRecording && activations == 1 && deactivations == 6,
                 "denied permission must release startup without activating audio")

    UserDefaults.standard.removeObject(forKey: "omiOwnerUID")
    recorder.startRecording()
    permissions.removeFirst()(true)
    precondition(!recorder.isRecording && activations == 1 && deactivations == 7,
                 "an unbound account must never activate audio")

    let output = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("watch-controls-result.json")
    try JSONSerialization.data(withJSONObject: [
        "passed": true, "cases": 7, "activationAttempts": activations,
        "deactivations": deactivations, "physicalAudio": false
    ]).write(to: output, options: .atomic)
}

@MainActor
final class ControlsFixture: WatchRecorderControlling {
    @Published var isRecording = !ProcessInfo.processInfo.arguments.contains("--idle")
    @Published var recordingStartedAt: Date? = ProcessInfo.processInfo.arguments.contains("--idle")
        ? nil : Date().addingTimeInterval(-2397)
    @Published var pendingRecoverySegments = ProcessInfo.processInfo.arguments.contains("--no-pending") ? 0 : 40
    var recoveryError: String? {
        ProcessInfo.processInfo.arguments.contains("--error") ? String(localized: "watch.recovery.savedAudioError") : nil
    }
    func startRecording() { isRecording = true; recordingStartedAt = Date() }
    func stopRecording() { isRecording = false; recordingStartedAt = nil }
    func retryRecoveryTransfers() {}
}

@main
struct WatchControlsProbeApp: App {
    @StateObject private var recorder = ControlsFixture()
    var body: some Scene {
        WindowGroup {
            WatchRecorderView(viewModel: recorder)
                .environment(\.dynamicTypeSize, ProcessInfo.processInfo.arguments.contains("--large-type") ? .accessibility3 : .large)
                .task {
                    if ProcessInfo.processInfo.arguments.contains("--verify-lifecycle") {
                        do { try verifyRecorderLifecycle() }
                        catch { preconditionFailure("Watch controls probe failed: \(error)") }
                    }
                }
        }
    }
}
