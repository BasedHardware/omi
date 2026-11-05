import AVFoundation
import Foundation
import Observation
import WatchKit

/// One recording at a time from the watch microphone, streamed to the Omi iPhone app. The iPhone can
/// also start and stop it, or refuse it (then `notice` says why).
@MainActor
@Observable
final class WatchRecorder {
    enum Phase: Equatable {
        case idle
        case starting
        case recording(since: Date)
    }

    enum Notice: Equatable {
        case microphoneDenied, microphoneFailed, phoneBusy, phoneSignedOut, phoneFailed
    }

    private(set) var phase: Phase = .idle
    private(set) var notice: Notice?
    /// What the iPhone reported last (capture and the Omi's battery).
    private(set) var phone: WatchPhoneState?

    @ObservationIgnored private let connection: WatchConnection
    @ObservationIgnored private let microphone: WatchMicrophone
    @ObservationIgnored private var tasks: [Task<Void, Never>] = []

    /// How often the watch battery goes to the iPhone (Flutter: 3 minutes).
    private static let batteryInterval: Duration = .seconds(180)

    init() {
        let connection = WatchConnection()
        self.connection = connection
        microphone = WatchMicrophone { chunk in connection.send(.audioChunk(chunk)) }
        connection.activate()
        tasks.append(Task { [weak self] in
            for await message in connection.messages {
                await self?.handle(message)
            }
        })
        tasks.append(Task { [weak self] in
            for await state in connection.phoneStates {
                self?.phone = state
            }
        })
        tasks.append(Task { [weak self] in
            self?.sendWatchInfo()
            while !Task.isCancelled {
                self?.sendBattery()
                try? await Task.sleep(for: Self.batteryInterval)
            }
        })
    }

    var isRecording: Bool {
        phase != .idle
    }

    func toggle() {
        if isRecording {
            stop(notifyPhone: true)
        } else {
            Task { await start() }
        }
    }

    func start() async {
        guard phase == .idle else { return }
        notice = nil
        phase = .starting
        guard await microphonePermission() else {
            phase = .idle
            notice = .microphoneDenied
            connection.send(.recordingError("Microphone permission denied"))
            return
        }
        // Before any audio: the iPhone opens the conversation on `startRecording`.
        connection.beginRecording()
        connection.send(.startRecording)
        do {
            try microphone.start()
        } catch {
            phase = .idle
            notice = .microphoneFailed
            connection.send(.recordingError("Microphone unavailable"))
            connection.send(.stopRecording(reason: nil))
            return
        }
        phase = .recording(since: .now)
        WKInterfaceDevice.current().play(.start)
    }

    /// - Parameter notifyPhone: false when the iPhone itself asked to stop.
    func stop(notifyPhone: Bool, reason: WatchStopReason? = nil) {
        guard case .recording = phase else { return }
        microphone.stop()
        if notifyPhone { connection.send(.stopRecording(reason: nil)) }
        phase = .idle
        notice = reason.map(Self.notice)
        WKInterfaceDevice.current().play(.stop)
    }

    private func handle(_ message: WatchMessage) async {
        switch message {
        case .startRecording:
            await start()
        case let .stopRecording(reason):
            stop(notifyPhone: false, reason: reason)
        case .requestMicrophonePermission:
            let granted = await microphonePermission()
            connection.send(.microphonePermissionResult(granted: granted))
        case .requestBattery:
            sendBattery()
        case .requestWatchInfo:
            sendWatchInfo()
        case .audioChunk, .recordingError, .microphonePermissionResult, .batteryUpdate, .watchInfoUpdate:
            break
        }
    }

    private func microphonePermission() async -> Bool {
        switch AVAudioApplication.shared.recordPermission {
        case .granted: true
        case .undetermined: await AVAudioApplication.requestRecordPermission()
        default: false
        }
    }

    private func sendBattery() {
        let device = WKInterfaceDevice.current()
        device.isBatteryMonitoringEnabled = true
        connection.send(.batteryUpdate(level: Double(device.batteryLevel * 100), state: device.batteryState.rawValue))
    }

    private func sendWatchInfo() {
        let device = WKInterfaceDevice.current()
        connection.send(.watchInfoUpdate(WatchInfo(
            name: device.name, model: device.model, systemVersion: device.systemVersion, localizedModel: device.localizedModel
        )))
    }

    private static func notice(_ reason: WatchStopReason) -> Notice {
        switch reason {
        case .busy: .phoneBusy
        case .signedOut: .phoneSignedOut
        case .failed: .phoneFailed
        }
    }
}
