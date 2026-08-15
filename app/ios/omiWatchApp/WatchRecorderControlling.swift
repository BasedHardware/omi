import Combine
import Foundation

@MainActor
protocol WatchRecorderControlling: ObservableObject {
    var isRecording: Bool { get }
    var recordingStartedAt: Date? { get }

    func startRecording()
    func stopRecording()
}
