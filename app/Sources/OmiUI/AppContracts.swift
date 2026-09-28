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

    @Published public internal(set) var outcomes: DesktopReadOutcomes?
    @Published public internal(set) var readsLoading: Bool = false
    @Published public internal(set) var tasksRead: TaskRead?
    @Published public internal(set) var chatMessages: [ChatMessage] = []
    @Published public internal(set) var chatHistoryLoading: Bool = false
    @Published public internal(set) var chatGeneration: ChatGenerationUiState = .idle
    @Published public var composerText: String = ""

    // MARK: Session

    @Published public internal(set) var authState: AuthUiState = .signedOut
    @Published public internal(set) var signInErrorCopy: String?

    // MARK: Devices

    @Published public internal(set) var bluetoothState: BluetoothState = .unknown
    @Published public internal(set) var discoveredDevices: [DiscoveredDevice] = []
    @Published public internal(set) var scanning: Bool = false
    @Published public internal(set) var connectingDeviceId: String?
    @Published public internal(set) var connectedDeviceName: String?
    @Published public internal(set) var connectedDeviceInfo: BleDeviceInfo?
    @Published public internal(set) var batteryLevel: Int?
    @Published public internal(set) var captureStage: CaptureStage = .idle
    @Published public internal(set) var deviceErrorCopy: String?

    // MARK: Rewind (desktop activity)

    @Published public internal(set) var rewindGroups: [RewindCaptureGroup] = []

    // MARK: Preferences + cloud

    @Published public internal(set) var preferences = DesktopPreferences()
    @Published public internal(set) var connectors: ConnectorsSnapshot?
    @Published public internal(set) var accountSettings: AccountSettingsSnapshot?
    @Published public internal(set) var cloudLoading: Bool = false

    // MARK: Intent surface (implemented in App/AppStore.swift)

    // MARK: Reads phase + pagination (useDesktopReads.ts)

    @Published public internal(set) var readsPhase: ReadsPhase = .initialLoading
    @Published public internal(set) var conversationsLoadingMore: Bool = false
    @Published public internal(set) var tasksLoadingMore: Bool = false
    @Published public internal(set) var conversationNotice: String?
    @Published public internal(set) var taskNotice: String?
    /// Conversations gained extra pages in this session (preserves loaded
    /// pages across refresh until the surface leaves and reopens).
    @Published public internal(set) var conversationsExtended: Bool = false

    // MARK: Memories pagination (loadOlderMemories)

    @Published public internal(set) var memoriesLoadingMore: Bool = false
    @Published public internal(set) var memoriesNotice: String?

    // MARK: Connectors page-level failure (refreshConnectors / toggles)

    @Published public internal(set) var connectorsErrorCopy: String?

    // MARK: Chat streaming bookkeeping

    @Published public internal(set) var chatBusy: Bool = false
    @Published public internal(set) var chatErrorCopy: String?
    @Published public internal(set) var hasOlderChat: Bool = false
    @Published public internal(set) var olderChatCursor: String?
    @Published public internal(set) var loadingOlderChat: Bool = false
    @Published public internal(set) var activeGenerationId: String?
    @Published public internal(set) var chatHistorySettled: Bool = false

    // MARK: Onboarding / session (useOnboarding.ts)

    /// nil = still probing; the shell must not claim either state yet.
    @Published public internal(set) var onboardingRequired: Bool?
    @Published public internal(set) var setupRequired: Bool = false
    @Published public internal(set) var completingSetup: Bool = false
    @Published public internal(set) var signingIn: Bool = false
    @Published public internal(set) var returningUser: Bool = false
    @Published public internal(set) var authErrorCopy: String?
    @Published public internal(set) var desktopHandoff: DesktopHandoff?
    @Published public internal(set) var postSetupHomeCue: PostSetupHomeCue?

    // MARK: Devices (useNativeDevices.ts)

    @Published public internal(set) var deviceBusy: Bool = false
    @Published public internal(set) var deviceScanMessage: String?
    @Published public internal(set) var rememberedDevice: DiscoveredDevice?

    // MARK: Preferences + cloud

    @Published public internal(set) var preferencesLoaded: Bool = false

    // MARK: Task mutations (useTaskMutations.ts)

    @Published public internal(set) var busyTaskId: String?
    @Published public internal(set) var taskMutationErrorCopy: String?
    @Published public internal(set) var canRetryTaskMutation: Bool = false

    // MARK: Rewind capture (useRewindCapture.ts)

    @Published public internal(set) var rewindCaptureState = RewindCaptureState()

    // MARK: Composition surface

    @Published public var homeChatOpen: Bool = false

    /// Injected service facades. Hosts wire real implementations at
    /// bootstrap; surfaces never touch transports directly.
    public var services = AppServices()

    /// Non-published orchestration internals (sequence fences, epochs,
    /// in-flight handles). MainActor-confined with the store.
    var runtime = AppRuntime()

    // MARK: Derived helpers (pure, used by both surfaces)

    /// The merged timeline feed (conversations + memories + tasks + capture
    /// groups), query-matched — the desktop Activity and mobile home lists.
    public func mergedTimeline(filter: TimelineFilter = .all) -> MergedTimeline {
        mergeTimeline(
            outcomes, query: searchQuery,
            captures: captureSummaries(from: rewindGroups), filter: filter)
    }

    public static let quickPrompts: [QuickPrompt] = [
        QuickPrompt("What did I talk about today?"),
        QuickPrompt("Show my pending tasks"),
        QuickPrompt("What should I remember?"),
        QuickPrompt("Summarize my recent conversations"),
    ]
}
