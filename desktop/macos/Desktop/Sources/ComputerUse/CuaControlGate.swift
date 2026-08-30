import ApplicationServices
import Foundation

/// Whether anything is allowed to drive this Mac, and who said so.
///
/// Computer control is the one tool surface where a mistake is not a bad answer
/// but a click on the user's desk. Three things have to hold before a synthetic
/// event is posted, and they are all here so no caller can hold two of them and
/// assume the third:
///
///   1. **The user turned it on.** Off by default, one explicit toggle, and the
///      toggle is per-account: the grant is bound to the owner who gave it, so
///      switching accounts closes the gate rather than inheriting consent.
///   2. **Nobody hit the kill switch.** A suspend is sticky. It survives until a
///      person re-arms it, because the reason to hit it is that something is
///      going wrong and a gate that re-opens on a timer is not a kill switch.
///   3. **The permission actually exists.** Accessibility is what makes a posted
///      event land; without it every click silently does nothing, which reads to
///      a model as a click that worked.
///
/// The gate is `@MainActor` on purpose. Checking here and posting the event
/// somewhere else leaves a window for an account switch to interleave; the
/// existing physical-effect fence has the same shape for the same reason.
@MainActor
final class CuaControlGate: ObservableObject {
  static let shared = CuaControlGate()

  /// Why the gate is closed, in the words the tool result will carry.
  enum Refusal: Error, Equatable {
    case disabled
    case suspended(reason: String)
    case ownerChanged
    case accessibilityMissing

    var message: String {
      switch self {
      case .disabled:
        return
          "Computer control is off. Turn on \"Allow Omi to control this Mac\" in Omi ▸ Settings ▸ Apps."
      case .suspended(let reason):
        return "Computer control was stopped (\(reason)). Re-arm it in Omi ▸ Settings ▸ Apps."
      case .ownerChanged:
        return "Computer control was granted by a different account. Turn it on again for this one."
      case .accessibilityMissing:
        return
          "Accessibility permission is missing, so input events would do nothing. Grant it in System Settings ▸ Privacy & Security ▸ Accessibility."
      }
    }
  }

  fileprivate enum Keys {
    static let enabled = "computerUseControlEnabled"
    static let owner = "computerUseControlOwnerID"
  }

  /// Posted whenever the gate opens or closes, so the indicator and the kill
  /// switch registration follow the state instead of polling it.
  nonisolated static let stateChanged = Notification.Name("CuaControlGateStateChanged")

  private let defaults: UserDefaults
  private let accessibilityIsTrusted: @MainActor () -> Bool
  private let ownerID: @MainActor () -> String?

  @Published private(set) var suspension: String?
  /// When a synthetic event was last posted, for the "active" indicator.
  @Published private(set) var lastActivity: Date?

  init(
    defaults: UserDefaults = .standard,
    accessibilityIsTrusted: @escaping @MainActor () -> Bool = { AXIsProcessTrusted() },
    ownerID: @escaping @MainActor () -> String? = {
      RuntimeOwnerIdentity.currentOwnerId(defaults: .standard)
    }
  ) {
    self.defaults = defaults
    self.accessibilityIsTrusted = accessibilityIsTrusted
    self.ownerID = ownerID
  }

  /// Whether the user has turned control on for the account signed in now.
  var isEnabled: Bool {
    defaults.bool(forKey: Keys.enabled) && grantedOwnerMatches
  }

  /// The same question, answerable from any thread. Both halves are plain
  /// defaults reads; the actor isolation on the rest of this type is about
  /// keeping a check and an event posted together, which a switch registration
  /// is not doing.
  nonisolated static func isEnabledForCurrentOwner(defaults: UserDefaults = .standard) -> Bool {
    guard defaults.bool(forKey: Keys.enabled) else { return false }
    let granted = defaults.string(forKey: Keys.owner)?.trimmingCharacters(in: .whitespacesAndNewlines)
    guard let granted, !granted.isEmpty else { return false }
    return granted
      == RuntimeOwnerIdentity.currentOwnerId(defaults: defaults)?
      .trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private var grantedOwnerMatches: Bool {
    let granted = defaults.string(forKey: Keys.owner)?.trimmingCharacters(in: .whitespacesAndNewlines)
    guard let granted, !granted.isEmpty else { return false }
    return granted == ownerID()?.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  /// Turn control on for the current account, or off. Enabling clears a suspend:
  /// it is the same deliberate act as re-arming.
  func setEnabled(_ enabled: Bool) {
    defaults.set(enabled, forKey: Keys.enabled)
    if enabled {
      defaults.set(ownerID() ?? "", forKey: Keys.owner)
      suspension = nil
    } else {
      defaults.removeObject(forKey: Keys.owner)
    }
    objectWillChange.send()
    NotificationCenter.default.post(name: Self.stateChanged, object: nil)
  }

  /// Stop everything now. Sticky until someone re-arms.
  func suspend(reason: String) {
    guard suspension == nil else { return }
    suspension = reason
    log("CuaControlGate: suspended — \(reason)")
    NotificationCenter.default.post(name: Self.stateChanged, object: nil)
  }

  func rearm() {
    guard suspension != nil else { return }
    suspension = nil
    NotificationCenter.default.post(name: Self.stateChanged, object: nil)
  }

  /// The reason a physical effect may not run, or nil when it may.
  ///
  /// Reads-only tools (a screenshot, an accessibility snapshot) ask for
  /// `requiresAccessibility: false` when they do not need to post anything, so a
  /// missing Accessibility grant does not blind a model that could still look.
  func refusal(requiresAccessibility: Bool = true) -> Refusal? {
    if let suspension { return .suspended(reason: suspension) }
    guard defaults.bool(forKey: Keys.enabled) else { return .disabled }
    guard grantedOwnerMatches else { return .ownerChanged }
    if requiresAccessibility, !accessibilityIsTrusted() { return .accessibilityMissing }
    return nil
  }

  /// Runs `effect` only while the gate is open, marking the surface active.
  /// Synchronous and `@MainActor`, so nothing can interleave between the check
  /// and the event.
  func perform<T: Sendable>(requiresAccessibility: Bool = true, _ effect: @Sendable () -> T)
    -> Result<T, Refusal>
  {
    if let refusal = refusal(requiresAccessibility: requiresAccessibility) {
      return .failure(refusal)
    }
    let value = effect()
    lastActivity = Date()
    return .success(value)
  }

  /// Marks the surface active for an effect that ran somewhere else — an
  /// accessibility press, which is a real action on the user's Mac even though
  /// it posts no event.
  func noteActivity() {
    lastActivity = Date()
  }
}
