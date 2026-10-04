import AppKit
import Combine

@MainActor
final class ProactivityFeedConsumer {
  static let shared = ProactivityFeedConsumer()
  private var observers = Set<AnyCancellable>()
  private var timer: Timer?
  private var store: ProactivityReceiptStore?
  private var authorization: RuntimeOwnerAuthorizationSnapshot?
  private var work: Task<Void, Never>?
  private var pendingPresentations = Set<String>()
  private var lastAttempt = Date.distantPast
  private var started = false
  private var pushRefreshPending = false
  private let journalURL: URL

  init(journalURL: URL? = nil) {
    self.journalURL =
      journalURL
      ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
      .appendingPathComponent(Bundle.main.bundleIdentifier ?? "omi")
      .appendingPathComponent("proactivity-receipts.json")
  }

  func start() {
    if !started {
      started = true
      NotificationCenter.default.publisher(for: .runtimeOwnerDidChange).sink { [weak self] _ in
        MainActor.assumeIsolated { self?.purgeForOwnerTransition() }
      }.store(in: &observers)
      NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification).sink { [weak self] _ in
        MainActor.assumeIsolated { self?.refresh() }
      }.store(in: &observers)
      timer = Timer.scheduledTimer(withTimeInterval: 600, repeats: true) { [weak self] _ in
        Task { @MainActor in if NSApp.isActive { self?.refresh() } }
      }
    }
    refresh()
  }

  /// The central owner transition calls this even before the admitted shell starts.
  /// A cold sign-out must delete a journal left by the previous process too.
  func purgeForOwnerTransition() {
    work?.cancel()
    work = nil
    do {
      try store?.purge()
      try ProactivityReceiptStore.purge(at: journalURL)
    } catch { log("Proactivity: receipt purge failed") }
    store = nil
    authorization = nil
    pendingPresentations.removeAll()
    lastAttempt = .distantPast
    pushRefreshPending = false
  }

  static func isListenWakeup(_ payload: [String: Any]) -> Bool {
    let type = payload["type"] as? String
    let v2 =
      type == "proactivity_v2"
      || (type == "proactive_message" && payload["notification_type"] as? String == "proactivity_v2")
    guard v2, let itemID = payload["item_id"] as? String, !itemID.isEmpty,
      let targetID = payload["target_id"] as? String, !targetID.isEmpty,
      let kind = payload["target_kind"] as? String
    else { return false }
    return kind == "conversation" || kind == "action_item"
  }

  func handleListenEvent(_ payload: [String: Any]) {
    guard Self.isListenWakeup(payload) else { return }
    pushRefreshPending = true
    refresh()
  }

  /// Push/listen wakeups fetch the authoritative feed; push copy never bypasses receipts.
  func refresh() {
    guard AccountCutoverControlManager.shared.isProductShellAdmitted,
      let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(), work == nil,
      pushRefreshPending || Date().timeIntervalSince(lastAttempt) >= 30
    else { return }
    if authorization != snapshot {
      if authorization != nil { purgeForOwnerTransition() }
      do {
        store = try ProactivityReceiptStore(url: journalURL, ownerID: snapshot.ownerID)
        authorization = snapshot
      } catch {
        log("Proactivity: receipt storage unavailable")
        return
      }
    }
    lastAttempt = Date()
    pushRefreshPending = false
    work = Task { [weak self] in
      guard let self else { return }
      await poll(snapshot)
      if authorization == snapshot {
        work = nil
        if pushRefreshPending { refresh() }
      }
    }
  }

  private func client(_ snapshot: RuntimeOwnerAuthorizationSnapshot) async throws -> OmiAPI.OmiApiClient {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot), !Task.isCancelled else {
      throw AuthError.userChangedDuringRequest
    }
    let api = APIClient.shared
    let headers = try await api.buildHeaders(
      requireAuth: true, includeBYOK: false, expectedAuthOwnerId: snapshot.ownerID)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot), !Task.isCancelled else {
      throw AuthError.userChangedDuringRequest
    }
    return OmiAPI.OmiApiClient(baseURL: await api.baseURL, headers: headers)
  }

  private func flush(_ snapshot: RuntimeOwnerAuthorizationSnapshot) async throws {
    try await store?.drain(isCurrent: { RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot) && !Task.isCancelled }) {
      entry in
      let api = try await client(snapshot)
      do {
        _ = try await OmiAPI.recordProactivityOutcome(
          client: api, itemId: entry.itemID, xAppPlatform: "macos", body: entry.request)
      } catch OmiAPI.OmiApiError.httpError(let status, _) where status == 404 {
        // Deleted source / expired server item: terminal, without retrying forever.
      }
    }
  }

  private func poll(_ snapshot: RuntimeOwnerAuthorizationSnapshot) async {
    do {
      try await flush(snapshot)
      guard pendingPresentations.isEmpty else { return }
      var cursor: String?
      // Bounded catch-up. A fresh poll starts at the newest page every time.
      for _ in 0..<5 {
        let api = try await client(snapshot)
        let feed = try await OmiAPI.getProactivityFeed(client: api, limit: 50, cursor: cursor, xAppPlatform: "macos")
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot), !Task.isCancelled, feed.enabled else { return }
        for item in feed.items {
          guard let deadline = ProactivityFreshness.deadline(createdAt: item.createdAt, serverTime: feed.serverTime),
            deadline > Date(), store?.hasShown(item.id) == false,
            !pendingPresentations.contains(item.id), ProactivityNotificationAdapter.target(for: item) != nil
          else { continue }
          pendingPresentations.insert(item.id)
          ProactivityNotificationAdapter.present(
            item, authorizationSnapshot: snapshot,
            hasBeenPresented: { self.store?.hasShown($0) != false },
            channel: "feed", expiresAt: deadline,
            onDropped: { [weak self] in self?.pendingPresentations.remove(item.id) },
            onOutcome: { [weak self] id, request in
              guard let self, RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot) else { return }
              do { try store?.record(itemID: id, request: request) } catch {
                log("Proactivity: outcome persistence failed")
              }
              if request.action == "shown" { pendingPresentations.remove(id) }
              // The next bounded poll retries failures with the same durable event ID.
              Task { [weak self] in try? await self?.flush(snapshot) }
            })
          // Shared pacing is stamped at render, not queue admission. A feed
          // page must not enqueue a burst before its first card mounts.
          return
        }
        guard feed.hasMore, !feed.nextCursor.isEmpty else { break }
        cursor = feed.nextCursor
      }
    } catch { log("Proactivity: feed/outcome request deferred for retry") }
  }
}
