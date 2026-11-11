import Combine
import Foundation

@MainActor
protocol WatchRecorderControlling: ObservableObject {
    var isRecording: Bool { get }
    var recordingStartedAt: Date? { get }
    var pendingRecoverySegments: Int { get }
    var recoveryError: String? { get }

    func startRecording()
    func stopRecording()
    func retryRecoveryTransfers()
}

extension WatchRecorderControlling {
    func retryRecoveryTransfers() {}
    var pendingRecoverySegments: Int { 0 }
    var recoveryError: String? { nil }
}
