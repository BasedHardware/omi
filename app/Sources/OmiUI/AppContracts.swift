import OmiKit
import SwiftUI

// The composition contract for the app wave: one observable store owning the
// AppOrchestrator state machine (routes, reads, chat, onboarding, devices,
// capture, rewind, preferences, connectors) over the OmiKit service facades.
// `App/AppStore.swift` implements it; `Mobile/` and `Desktop/` render it via
// @EnvironmentObject. Keep the shipped names here stable — both surfaces and
// the hosts depend on them.

/// Top-level routes, matching `app/routes.ts`.
public enum AppRoute: String, Sendable, Hashable, CaseIterable {
    case home = "Home"
    case conversations = "Conversations"
    case memories = "Memories"
    case tasks = "Tasks"
    case settings = "Settings"
    case connectors = "Connectors"
}

/// Mobile tab routes, matching `MobileRoute` in `MobileAppSurface.tsx`.
public enum MobileRoute: String, Sendable, Hashable, CaseIterable {
    case home
    case chat
    case tasks
    case settings
    case apps

    /// Paired, exhaustive Route <-> MobileRoute map (AppOrchestrator.tsx):
    /// Memories has no mobile surface of its own and lands on the home route.
    public init(_ route: AppRoute) {
        switch route {
        case .home, .memories: self = .home
        case .conversations: self = .chat
        case .tasks: self = .tasks
        case .settings: self = .settings
        case .connectors: self = .apps
        }
    }

    public var appRoute: AppRoute {
        switch self {
        case .home: return .home
        case .chat: return .conversations
        case .tasks: return .tasks
        case .settings: return .settings
        case .apps: return .connectors
        }
    }
}

/// Sign-in/onboarding presentation state.
public enum AuthUiState: Sendable, Equatable {
    case signedOut
    case signingIn
    case onboarding
    case signedIn
}

/// Home-screen connection summary, mirroring `homeConnectionStatus` in
/// `app/DeviceSession.tsx`.
public enum HomeConnectionStatus: Sendable, Equatable {
    case disconnected
    case scanning
    case connecting
    case connected
    case waitingForAudio
}

/// Live chat generation state for the transcript surfaces.
public enum ChatGenerationUiState: Sendable, Equatable {
    case idle
    /// Waiting for the first streamed token after admission.
    case pending
    /// Streaming; carries the latest visible assistant text.
    case streaming(String)
}

/// A quick prompt shown on the empty home/chat surfaces.
public struct QuickPrompt: Sendable, Hashable, Identifiable {
    public var id: String { text }
    public var text: String

    public init(_ text: String) {
        self.text = text
    }
}

/// The app state machine. All OmiKit access funnels through here — views
/// never touch `BackendTransport`, credentials, or the device transport
/// directly.
@MainActor
public final class AppStore: ObservableObject {
    // MARK: Routing

    @Published public var route: AppRoute = .home
    @Published public var mobileRoute: MobileRoute = .home
    /// Omnibar mode is Search (not Recall) on the desktop surface.
    @Published public var searchQuery: String = ""
    @Published public var searchActive: Bool = false

    public init() {}

    // MARK: Reads (conversations / memories / tasks)

    @Published public private(set) var outcomes: DesktopReadOutcomes?
    @Published public private(set) var readsLoading: Bool = false
    @Published public private(set) var tasksRead: TaskRead?
    @Published public private(set) var chatMessages: [ChatMessage] = []
    @Published public private(set) var chatHistoryLoading: Bool = false
    @Published public private(set) var chatGeneration: ChatGenerationUiState = .idle
    @Published public var composerText: String = ""

    // MARK: Session

    @Published public private(set) var authState: AuthUiState = .signedOut
    @Published public private(set) var signInErrorCopy: String?

    // MARK: Devices

    @Published public private(set) var bluetoothState: BluetoothState = .unknown
    @Published public private(set) var discoveredDevices: [DiscoveredDevice] = []
    @Published public private(set) var scanning: Bool = false
    @Published public private(set) var connectingDeviceId: String?
    @Published public private(set) var connectedDeviceName: String?
    @Published public private(set) var connectedDeviceInfo: BleDeviceInfo?
    @Published public private(set) var batteryLevel: Int?
    @Published public private(set) var captureStage: CaptureStage = .idle
    @Published public private(set) var deviceErrorCopy: String?

    // MARK: Rewind (desktop activity)

    @Published public private(set) var rewindGroups: [RewindCaptureGroup] = []

    // MARK: Preferences + cloud

    @Published public private(set) var preferences = DesktopPreferences()
    @Published public private(set) var connectors: ConnectorsSnapshot?
    @Published public private(set) var accountSettings: AccountSettingsSnapshot?
    @Published public private(set) var cloudLoading: Bool = false

    // MARK: Intent surface (implemented in App/AppStore.swift)

    public func navigate(_ route: AppRoute) {}
    public func navigate(mobileRoute: MobileRoute) {}

    public func refreshReads() async {}
    public func loadOlderConversations() async {}
    public func loadOlderMemories() async {}
    public func loadOlderTasks() async {}

    public func sendChat(_ text: String) async {}
    public func cancelChatGeneration() async {}
    public func loadOlderChatHistory() async {}

    public func toggleTask(_ task: TaskProjection) async {}
    public func renameTask(_ task: TaskProjection, title: String) async {}
    public func addTask(title: String) async {}

    public func startSignIn() async {}
    public func cancelSignIn() {}
    public func completeOnboarding() async {}
    public func signOut() async {}

    public func startScan() async {}
    public func stopScan() {}
    public func connect(_ device: DiscoveredDevice) async {}
    public func disconnectDevice() async {}

    public func refreshConnectors() async {}
    public func enableConnector(appId: String) async {}
    public func disableConnector(appId: String) async {}
    public func setStoreRecordingPermission(_ value: Bool) async {}
    public func setPrivateCloudSync(_ value: Bool) async {}
    public func optInTrainingData() async {}
    public func setPreference(_ key: String, _ value: PreferenceValue) async {}
    public func requestPermission(_ kind: PermissionKind) async {}

    // MARK: Derived helpers (pure, used by both surfaces)

    /// The merged timeline feed (conversations + memories + tasks + capture
    /// groups), query-matched — the desktop Activity and mobile home lists.
    public func mergedTimeline(filter: TimelineFilter = .all) -> MergedTimeline {
        mergeTimeline(outcomes, query: searchQuery, filter: filter)
    }

    public static let quickPrompts: [QuickPrompt] = [
        QuickPrompt("What did I talk about today?"),
        QuickPrompt("Show my pending tasks"),
        QuickPrompt("What should I remember?"),
        QuickPrompt("Summarize my recent conversations"),
    ]
}
