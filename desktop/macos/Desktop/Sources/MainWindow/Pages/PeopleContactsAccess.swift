import AppKit
import Contacts
import Foundation

/// Where the People tab's **names** come from, as one explicit state.
///
/// iMessage stores 1:1 threads by phone number only — its export carries no `contact_name` (unlike
/// WhatsApp, which ships `ZPARTNERNAME`). Contacts is therefore the only thing that can turn
/// `+15551234567` into "Alice Nguyen", and everything downstream depends on that name existing:
/// `PeopleMemoryWriter.isHumanName` drops digit-only names (→ no relationship facts) and
/// `PeopleThreadIngest.readThreadCandidates` only ingests threads whose phone resolves to a contact
/// (→ no deep understanding). A first run that races the permission prompt therefore produces a
/// list of raw phone numbers and nothing else.
///
/// Modelling access as a value (rather than an implicit `[:]` from `loadContactsByPhone`) makes the
/// difference between "not asked yet", "waiting on the user", and "the user said no" legible to the
/// pipeline *and* to the UI, so the tab can say why everyone is a phone number instead of silently
/// listing them. Everything stays on-device; nothing here is logged or sent anywhere.
enum PeopleContactsAccess: String, Sendable {
  /// On-device message mapping is off, so Contacts has never been asked for. Not a problem state.
  case notRequested
  /// The system prompt is up (or was dismissed without an answer): names may still arrive.
  case pending
  case authorized
  /// The user said no. Terminal for this app until they change it in System Settings — macOS never
  /// re-prompts after a denial, so asking again is a no-op, not a retry.
  case denied
  /// Blocked by policy (MDM / parental controls). Same user-visible effect as `denied`.
  case restricted

  /// True only when iMessage people can actually be named on this machine.
  var namesResolvable: Bool { self == .authorized }

  /// True when names are known to be unavailable and will stay that way without user action.
  var namesUnavailable: Bool { self == .denied || self == .restricted }

  /// The one honest, non-nagging line the People UI shows when names are missing. `nil` when there
  /// is nothing to explain (authorized, or nothing was ever requested).
  var notice: String? {
    switch self {
    case .denied:
      return "Names need Contacts access — people from iMessage stay listed by phone number until you allow it."
    case .restricted:
      return "Contacts access is blocked on this Mac, so people from iMessage stay listed by phone number."
    case .pending:
      return "Waiting on Contacts access — people from iMessage stay listed by phone number until you allow it."
    case .authorized, .notRequested:
      return nil
    }
  }

  /// Only a denial/restriction is fixable in System Settings; a pending prompt is answered in place,
  /// so the UI must not offer a button that does nothing.
  var canOpenSettings: Bool { namesUnavailable }

  /// Pure mapping (no IO — unit-testable). `messageMappingEnabled` is the same on-device consent
  /// flag the exporters gate on: without it the pipeline never reads messages, so a missing Contacts
  /// grant is not a problem worth surfacing.
  static func state(status: CNAuthorizationStatus, messageMappingEnabled: Bool) -> PeopleContactsAccess {
    guard messageMappingEnabled else { return .notRequested }
    switch status {
    case .authorized: return .authorized
    case .denied: return .denied
    case .restricted: return .restricted
    case .notDetermined: return .pending
    // `.limited` (iOS 18+) and any future case: we cannot claim names are resolvable, but it is not
    // a denial either — treat it as still-undecided rather than asserting something false.
    default: return .pending
    }
  }

  /// Live state. Cheap (a TCC status read plus a defaults read) and never prompts, so any surface —
  /// including a view — can ask. Callers on the main actor should still hop off it out of habit.
  static func current() -> PeopleContactsAccess {
    state(
      status: CNContactStore.authorizationStatus(for: .contacts),
      messageMappingEnabled: UserDefaults.standard.bool(forKey: .peopleIMessageExport))
  }

  @MainActor
  static func openSettings() {
    guard
      let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Contacts")
    else { return }
    NSWorkspace.shared.open(url)
  }

  // MARK: - Bounded prompt

  /// How long one pipeline run waits for the user's answer before naming people without it. The
  /// prompt is modal to the *user*, not to us: past this window the run continues (phone-number
  /// labels) and a late "Allow" is applied by a one-shot re-run instead of a stalled pipeline.
  static let promptTimeout: Duration = .seconds(20)

  /// Resolve Contacts access for the naming pass, prompting at most once.
  ///
  /// - Already authorized / denied / restricted, or mapping consent off → returns immediately;
  ///   no prompt, no behavior change.
  /// - Undecided → shows the system prompt and waits up to `timeout` for the answer, so a first run
  ///   can name people instead of listing phone numbers.
  /// - Still unanswered at `timeout` → returns `.pending` (the caller proceeds), and when the answer
  ///   finally lands, a grant re-runs the naming pass exactly once via
  ///   `PeopleGraphBuilder.renameAfterContactsGrant`. A denial does nothing — never a nag loop.
  @discardableResult
  static func prepareForNaming(uid: String?, timeout: Duration = promptTimeout) async -> PeopleContactsAccess {
    let state = current()
    guard state == .pending else { return state }
    // One prompt at a time: the People tab, app-activation, and connector imports all fan into the
    // sync, and each of them re-asking would mean several late re-runs for one answer.
    guard await ContactsPromptGate.shared.begin() else { return .pending }

    let relay = ContactsPromptRelay(uid: uid)
    guard let granted = await awaitWithTimeout(timeout, operation: relay.request) else {
      relay.boundedWaitGaveUp()
      log("PeopleContactsAccess: Contacts prompt unanswered within the wait; naming without it")
      return .pending
    }
    await ContactsPromptGate.shared.end()
    return granted ? .authorized : .denied
  }
}

/// Serializes the one-time Contacts prompt across the many triggers that fan into
/// `PeopleGraphBuilder.syncIfNeeded`. Stays closed while a prompt is outstanding (including
/// indefinitely, if the user never answers) — which is the point: an unanswered prompt must not be
/// re-raised on every sync.
private actor ContactsPromptGate {
  static let shared = ContactsPromptGate()

  private var promptInFlight = false

  func begin() -> Bool {
    if promptInFlight { return false }
    promptInFlight = true
    return true
  }

  func end() { promptInFlight = false }
}

/// Bridges `CNContactStore.requestAccess` to async and keeps listening after the bounded wait gives
/// up, so an answer that arrives late still gets applied. Lock-guarded because the answer can land
/// on any queue; the late hand-off fires exactly once (whichever of the two sides observes the other
/// first triggers it).
private final class ContactsPromptRelay: @unchecked Sendable {
  private let uid: String?
  private let lock = NSLock()
  private var boundedWaitEnded = false
  private var decision: Bool?

  init(uid: String?) { self.uid = uid }

  @Sendable
  func request() async -> Bool {
    let store = CNContactStore()
    let granted = await withCheckedContinuation { (continuation: CheckedContinuation<Bool, Never>) in
      store.requestAccess(for: .contacts) { granted, _ in continuation.resume(returning: granted) }
    }
    // The store must outlive the request it issued; the completion handler deliberately captures
    // only the continuation (CNContactStore is not Sendable).
    withExtendedLifetime(store) {}
    record(granted)
    return granted
  }

  /// The run stopped waiting. If the answer already landed in the same instant, hand it off here.
  func boundedWaitGaveUp() {
    lock.lock()
    boundedWaitEnded = true
    let landed = decision
    lock.unlock()
    if let landed { finish(granted: landed) }
  }

  private func record(_ granted: Bool) {
    lock.lock()
    let late = boundedWaitEnded
    decision = granted
    lock.unlock()
    guard late else { return }
    finish(granted: granted)
  }

  private func finish(granted: Bool) {
    let uid = self.uid
    Task.detached(priority: .utility) {
      await ContactsPromptGate.shared.end()
      guard granted else { return }
      log("PeopleContactsAccess: Contacts allowed after the naming pass; re-running it")
      await PeopleGraphBuilder.renameAfterContactsGrant(uid: uid)
    }
  }
}
