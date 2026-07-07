import AppKit
import SwiftUI

/// Status of a capture-style feature as shown in the toolbar controls.
enum HomeStatusState {
    case active
    case inactive
    case blocked

    var indicator: Color {
        switch self {
        case .active:
            return HomePalette.green
        case .inactive:
            return HomePalette.faint
        case .blocked:
            return Color(red: 1.0, green: 0.24, blue: 0.30)
        }
    }

    var text: String {
        switch self {
        case .active:
            return "On"
        case .inactive:
            return "Off"
        case .blocked:
            return "Blocked"
        }
    }

    var isActive: Bool {
        if case .active = self { return true }
        return false
    }

    var isBlocked: Bool {
        if case .blocked = self { return true }
        return false
    }
}

/// Shared state + actions behind the Capture and Listening toolbar controls.
/// One instance per `ToolbarStatusControls`; the underlying truth lives in
/// `ProactiveAssistantsPlugin` / `AssistantSettings` / `AppState`, so
/// instances stay in sync via the monitoring notifications.
///
/// Extracted from `DashboardPage` so the window toolbar can host the
/// control cluster without duplicating the toggle logic.
@MainActor
final class CaptureListeningController: ObservableObject {
    @Published private(set) var isCaptureMonitoring = false
    @Published private(set) var isTogglingCapture = false
    @Published private(set) var isTogglingListening = false

    private let appState: AppState
    private var observers: [NSObjectProtocol] = []

    init(appState: AppState) {
        self.appState = appState
        syncCaptureState()

        let center = NotificationCenter.default
        let syncNames: [Notification.Name] = [
            .assistantMonitoringStateDidChange,
            .screenCapturePermissionLost,
            .screenCaptureKitBroken,
        ]
        for name in syncNames {
            observers.append(
                center.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                    Task { @MainActor in self?.syncCaptureState() }
                })
        }
    }

    deinit {
        for observer in observers {
            NotificationCenter.default.removeObserver(observer)
        }
    }

    // MARK: - State

    var isCaptureLive: Bool {
        isCaptureMonitoring || ProactiveAssistantsPlugin.shared.isMonitoring
    }

    var captureStatus: HomeStatusState {
        if appState.isScreenCaptureKitBroken || appState.isScreenRecordingStale
            || !appState.hasScreenRecordingPermission
        {
            return .blocked
        }
        return isCaptureLive ? .active : .inactive
    }

    var listeningCaptureMode: AssistantSettings.SystemAudioCaptureMode {
        AssistantSettings.shared.systemAudioCaptureMode
    }

    var listeningModeTitle: String {
        switch listeningCaptureMode {
        case .always:
            return "Always"
        case .onlyDuringMeetings:
            return appState.isAwaitingMeeting ? "Meetings only" : "In meeting"
        case .never:
            return "Mic only"
        }
    }

    // MARK: - Actions

    func toggleListening() {
        let enabled = !appState.isTranscribing
        if enabled && !appState.hasMicrophonePermission {
            appState.requestMicrophonePermission()
            return
        }

        isTogglingListening = true
        UserDefaults.standard.set(enabled, forKey: "transcriptionEnabled")
        AssistantSettings.shared.transcriptionEnabled = enabled
        AnalyticsManager.shared.settingToggled(setting: "transcription", enabled: enabled)
        NotificationCenter.default.post(
            name: .toggleTranscriptionRequested,
            object: nil,
            userInfo: ["enabled": enabled]
        )

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in
            self?.isTogglingListening = false
        }
    }

    func toggleListeningMode() {
        let nextMode: AssistantSettings.SystemAudioCaptureMode =
            listeningCaptureMode == .onlyDuringMeetings ? .always : .onlyDuringMeetings
        UserDefaults.standard.set(nextMode.rawValue, forKey: "systemAudioCaptureMode")
        AssistantSettings.shared.systemAudioCaptureMode = nextMode
        AnalyticsManager.shared.settingToggled(
            setting: "meetings_only_listening",
            enabled: nextMode == .onlyDuringMeetings
        )
        objectWillChange.send()
    }

    func toggleCapture() {
        syncCaptureState()
        let enabled = !isCaptureLive
        isTogglingCapture = true

        if enabled {
            ProactiveAssistantsPlugin.shared.refreshScreenRecordingPermission()
            guard ProactiveAssistantsPlugin.shared.hasScreenRecordingPermission else {
                setScreenAnalysisEnabled(false)
                isCaptureMonitoring = false
                isTogglingCapture = false
                ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
                return
            }
        }

        setScreenAnalysisEnabled(enabled)
        AnalyticsManager.shared.settingToggled(setting: "monitoring", enabled: enabled)

        if enabled {
            ProactiveAssistantsPlugin.shared.startMonitoring { [weak self] success, _ in
                DispatchQueue.main.async {
                    guard let self else { return }
                    self.isTogglingCapture = false
                    self.isCaptureMonitoring = ProactiveAssistantsPlugin.shared.isMonitoring
                    if !success {
                        self.setScreenAnalysisEnabled(false)
                        self.isCaptureMonitoring = false
                    }
                }
            }
        } else {
            ProactiveAssistantsPlugin.shared.stopMonitoring()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in
                self?.isTogglingCapture = false
                self?.isCaptureMonitoring = false
            }
        }
    }

    func syncCaptureState() {
        ProactiveAssistantsPlugin.shared.refreshScreenRecordingPermission()
        isCaptureMonitoring = ProactiveAssistantsPlugin.shared.isMonitoring
        objectWillChange.send()
    }

    private func setScreenAnalysisEnabled(_ enabled: Bool) {
        UserDefaults.standard.set(enabled, forKey: "screenAnalysisEnabled")
        AssistantSettings.shared.screenAnalysisEnabled = enabled
    }
}
