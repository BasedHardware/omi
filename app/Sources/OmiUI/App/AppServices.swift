import Foundation
import OmiKit

// Composition wiring for the app wave. Hosts construct `AppServices` with
// concrete implementations and hand it to `AppStore(services:)`; everything
// is optional so a host can come up feature-by-feature, and every absent
// dependency degrades honestly (no fake data, no fake progress).

/// Injected service facades. Hosts wire real implementations at bootstrap;
/// surfaces never touch transports directly.
///
/// `transport` is the raw authenticated backend transport. It is only needed
/// for the few intents that have no dedicated facade yet (the task-create
/// write op behind `addTask`, and Old-plane chat cancellation), so it
/// defaults to nil and the host may omit it.
public struct AppServices: Sendable {
    public var auth: (any Authenticating)?
    public var chat: ChatServicing?
    public var reads: ReadsServicing?
    public var tasks: TasksServicing?
    public var cloud: CloudServicing?
    public var settings: (any SettingsStoring)?
    public var devices: (any DeviceTransport)?
    public var rewindCapture: RewindCaptureControlling?
    public var transport: (any BackendTransport)?

    public init(
        auth: (any Authenticating)? = nil,
        chat: ChatServicing? = nil,
        reads: ReadsServicing? = nil,
        tasks: TasksServicing? = nil,
        cloud: CloudServicing? = nil,
        settings: (any SettingsStoring)? = nil,
        devices: (any DeviceTransport)? = nil,
        rewindCapture: RewindCaptureControlling? = nil,
        transport: (any BackendTransport)? = nil
    ) {
        self.auth = auth
        self.chat = chat
        self.reads = reads
        self.tasks = tasks
        self.cloud = cloud
        self.settings = settings
        self.devices = devices
        self.rewindCapture = rewindCapture
        self.transport = transport
    }
}

/// Non-published orchestration internals (sequence fences, epochs, in-flight
/// handles). MainActor-confined with the store.
final class AppRuntime {
    // Lifecycle
    var started = false
    var streamTasks: [Task<Void, Never>] = []

    // Auth / onboarding (useOnboarding.ts)
    var authOperation = 0
    /// Mirror of the persisted "onboarding completed" flag; the probe, sign-in
    /// and completion paths all read and write it.
    var completedOnboarding: Bool?
    var cueTracker = PostSetupHomeCueTracker()

    // Reads (useDesktopReads.ts)
    var refreshSeq = 0
    var refreshPending = false
    var conversationPagePending = false
    var taskPagePending = false
    var memoryPagePending = false
    var conversationsExtended = false
    var tasksExtended = false

    // Chat bookkeeping (AppOrchestrator.tsx)
    var chatSessionEpoch = 0
    /// Lock-free mirror for @Sendable chat callbacks (the synchronous
    /// request-started fence); updated only on the store's actor.
    var chatSessionEpochMirror = LockedBox(0)
    var chatMutationSeq = 0
    var sendInFlight = false
    var activeOmiRequestId: String?

    // Connectors
    var pendingConnectorId: String?

    // Task mutations (useTaskMutations.ts)
    var pendingTaskPatch: PreparedTaskPatch?
    var taskMutationActive = false
    var taskGeneration = 0
    var taskRetryAfterMs: Int64 = 0
    var taskAcknowledged = false

    // Devices (useNativeDevices.ts)
    var connectedDeviceId: String?
    var connectionId: String?
    var captureMachine: CaptureSessionMachine?
}

/// A locked mutable box so `@Sendable` service callbacks (chat streaming
/// fences) can read/write a value without data races. MainActor state is
/// updated only after re-marshalling onto the actor. Unconditionally
/// `@unchecked Sendable`: every stored value in this module is Sendable, and
/// Skip cannot transpile constrained protocol extensions.
final class LockedBox<Value>: @unchecked Sendable {
    private let lock = NSLock()
    private var value: Value

    init(_ value: Value) {
        self.value = value
    }

    func withLock<Return>(_ body: (inout Value) -> Return) -> Return {
        lock.lock()
        defer { lock.unlock() }
        return body(&value)
    }

    func get() -> Value {
        withLock { value in value }
    }

    func set(_ newValue: Value) {
        withLock { value in value = newValue }
    }
}
