import Foundation

/// The computer-control state the built-in server's surfaces render: the switch
/// and grants warning on its MCP card, and the permissions block in its detail
/// sheet.
///
/// One shared instance rather than per-view `@State`, because those surfaces
/// must agree with each other and with `CuaControlGate` at the same moment — a
/// card switch that disagrees with the sheet it opens is how a switch stops
/// being trusted. The gate stays the authority; this type adds only what
/// rendering needs: the switch position, the live grants behind the warning
/// chip, the last failure, and the enable/disable side effects (the loopback
/// token plus the mcp.json entry Omi's own agent reads).
@MainActor
final class CuaControlStatusStore: ObservableObject {
  static let shared = CuaControlStatusStore()

  /// The switch position as the UI holds it. A refused enable (no account
  /// signed in) corrects it back, which re-enters `didSet` once with the
  /// corrected value and settles — the same settle the dedicated section this
  /// replaced relied on.
  @Published var isEnabled: Bool {
    didSet {
      guard oldValue != isEnabled else { return }
      setEnabled(isEnabled)
    }
  }

  /// Every grant, checked with the API that actually answers for it. Input and
  /// UI reading are two TCC services behind one System Settings pane, so they
  /// are listed separately: a Mac can hold either without the other.
  @Published private(set) var granted: [CuaPermission: Bool] = [:]
  @Published private(set) var failure: String?

  /// Screen Recording ticked after this process launched: TCC says granted and
  /// capture is dead until Omi restarts. Its own state because it is neither of
  /// the two a checkbox can express, and reporting it as either one sends the
  /// user somewhere that cannot help.
  @Published private(set) var screenNeedsRelaunch = false

  /// One grant as the surfaces name it. A named type rather than a tuple
  /// because a row is passed to a view, and a three-part tuple in a view
  /// signature stops saying what it is.
  struct Listed {
    let permission: CuaPermission
    let title: String
    let detail: String
  }

  /// Two of these live in the same System Settings pane and are still two
  /// separate grants, so each is named by what it lets Omi do rather than by the
  /// pane it is found in.
  static let listed: [Listed] = [
    Listed(permission: .postEvents, title: "Input", detail: "move the pointer, click, and type"),
    Listed(
      permission: .accessibility, title: "Reading controls",
      detail: "read another app's controls and press them by name"),
    Listed(permission: .screenRecording, title: "Screen", detail: "take screenshots"),
  ]

  private var watchers = 0
  private var pollTask: Task<Void, Never>?

  private let gate: CuaControlGate
  private let isGranted: @MainActor (CuaPermission) -> Bool
  private let needsRelaunch: @MainActor () -> Bool

  init(
    gate: CuaControlGate = .shared,
    isGranted: @escaping @MainActor (CuaPermission) -> Bool = { $0.isGranted() },
    needsRelaunch: @escaping @MainActor () -> Bool = { CuaPermission.screenRecordingNeedsRelaunch }
  ) {
    self.gate = gate
    self.isGranted = isGranted
    self.needsRelaunch = needsRelaunch
    self.isEnabled = gate.isEnabled
    refreshPermissions()
  }

  /// How many of the listed grants macOS has not given. The card's warning chip
  /// exists so a missing permission is found on the Apps page, not discovered as
  /// a tool that silently does nothing.
  var missingGrantCount: Int {
    Self.listed.filter { !(granted[$0.permission] ?? false) }.count
  }

  var isSuspended: Bool { gate.suspension != nil }

  /// The built-in server's card status, in the same vocabulary every other
  /// server card uses. Gate state outranks everything — the same precedence the
  /// gate itself enforces — so an off or stopped server has no grants question
  /// worth asking.
  var cardStatusText: String {
    if !isEnabled { return "Off" }
    if isSuspended { return "Stopped" }
    if missingGrantCount > 0 {
      return "Needs \(missingGrantCount) grant\(missingGrantCount == 1 ? "" : "s")"
    }
    if screenNeedsRelaunch { return "Restart to apply" }
    return "Ready"
  }

  /// Active, the way a healthy server's tool count is active, only when the
  /// tools can actually run.
  var cardStatusActive: Bool {
    isEnabled && !isSuspended && missingGrantCount == 0 && !screenNeedsRelaunch
  }


  func stopNow() { gate.suspend(reason: "stopped from Settings") }
  func rearm() { gate.rearm() }

  /// Turning control on also starts the loopback server and writes the entry
  /// Omi's own agent reads, so one switch is the whole setup rather than three
  /// steps a user can complete two of.
  private func setEnabled(_ enabled: Bool) {
    failure = nil
    guard enabled else {
      gate.setEnabled(false)
      CuaMcpRegistration.unregister()
      return
    }
    do {
      let token = try LocalAgentAPISettings.enable()
      try CuaMcpRegistration.register(token: token)
      gate.setEnabled(true)
      isEnabled = gate.isEnabled
      if !isEnabled {
        failure = "Sign in to Omi first — computer control is granted per account."
      }
    } catch {
      failure = error.localizedDescription
      isEnabled = false
    }
  }

  /// Re-reads the grants and the switch. The live probe that feeds the
  /// accessibility grants is IPC and runs off the main actor (`poll`); the box
  /// ticked in System Settings is what this is watching for.
  func refreshPermissions() {
    // A plain literal, not `Dictionary(uniqueKeysWithValues:)`: that traps on a
    // duplicate key, and `listed` is a table someone will one day add a row to.
    var refreshed: [CuaPermission: Bool] = [:]
    for entry in Self.listed {
      refreshed[entry.permission] = isGranted(entry.permission)
    }
    granted = refreshed
    screenNeedsRelaunch = needsRelaunch()
    isEnabled = gate.isEnabled
  }

  /// Catches up with grants given while Omi was running, then refreshes.
  func poll() async {
    await CuaPermission.refreshLiveGrants([.accessibility, .postEvents])
    refreshPermissions()
  }

  /// One timer for however many surfaces are on screen.
  ///
  /// The card grid and the sheet both watch this state, and each owning a timer
  /// meant two accessibility probes every two seconds whenever the sheet was
  /// open over the grid. Callers say when they are watching instead; the poll
  /// runs while at least one is.
  func beginPolling() {
    watchers += 1
    guard pollTask == nil else { return }
    pollTask = Task { [weak self] in
      while !Task.isCancelled {
        await self?.poll()
        try? await Task.sleep(for: .seconds(2))
      }
    }
  }

  func endPolling() {
    watchers = max(0, watchers - 1)
    guard watchers == 0 else { return }
    pollTask?.cancel()
    pollTask = nil
  }

}
