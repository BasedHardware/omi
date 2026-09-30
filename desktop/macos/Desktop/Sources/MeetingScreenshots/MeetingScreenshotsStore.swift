//
//  MeetingScreenshotsStore.swift — one conversation's pictures, and the state of getting them.
//
//  The server is the source of truth for everything past selection: what got approved, the cap,
//  the banner, deletion, promotion after a delete. This store's job is narrower than it looks —
//  run on-device selection, hand the survivors to `MeetingFrameJudge`, and render the server's
//  verdict only when each frame remains inside the trusted transcript content window. It never
//  re-derives a quality verdict, and every failure path (no network, 4xx/5xx, an empty set) collapses to the same `.failed`
//  / `.noCapture` state a view renders as nothing — never an error card. A gate the user cannot see
//  the far side of must fail toward silence, not toward a broken-looking note.
//
//  The store is per-conversation and lives as long as the detail view. Results are memoised for the
//  session so reopening a note does not re-request it; `refreshPersistedSet()` busts that cache
//  deliberately, for a delete's promotion or an expired signed URL (`url_expires_at`, 60 minutes).
//

import Foundation
import SwiftUI

/// The feature gate. Server-controlled per the contract's `meeting_note_screenshots_enabled`
/// account setting (default true) — this mirrors it into `UserDefaults` so the check stays
/// synchronous, the same idiom `ChatToolExecutor.isChatScreenshotSharingEnabled` already uses for
/// the sibling screenshot-sharing grant. Off = the pipeline never runs, so a previously-persisted
/// set is never fetched and never rendered either ("existing frames stay hidden").
enum MeetingNoteScreenshotsFeature {
  nonisolated static var isEnabled: Bool {
    let defaults = UserDefaults.standard
    let stored: Bool? =
      defaults.object(forKey: DefaultsKey.meetingNoteScreenshotsEnabled) == nil
      ? nil : defaults.bool(forKey: DefaultsKey.meetingNoteScreenshotsEnabled)
    return isEnabled(storedValue: stored)
  }

  /// Pure for testing. Absent (`nil`) reads as on, matching the contract's default.
  static func isEnabled(storedValue: Bool?) -> Bool {
    storedValue ?? true
  }
}

@MainActor
final class MeetingScreenshotsStore: ObservableObject {

  enum Phase: Equatable {
    case idle
    case disabled
    /// Rewind has no frames inside this conversation's window, or the server approved none of
    /// what was uploaded. Both are common and neither is an error.
    case noCapture
    case selecting
    case judging(candidates: Int)
    case ready
    case failed(String)
  }

  @Published private(set) var phase: Phase = .idle
  @Published private(set) var frames: [ConversationScreenFrame] = []
  @Published private(set) var banner: ConversationScreenFrame?
  /// What on-device selection did, in the user's words.
  ///
  /// **Nothing renders this yet, deliberately.** The shipping design has a "how these were
  /// chosen" disclosure; this change does not have that surface yet. Keeping the record and
  /// writing it to the log is what makes selection auditable in the only place a developer can
  /// look today — a gate whose reasoning is invisible is a gate that looks like it is not needed.
  /// It stays `@Published` so the eventual disclosure needs no plumbing, not because a view reads
  /// it. It no longer describes enforcement — there is none left on this side of the network.
  @Published private(set) var diagnostics: [String] = []

  /// A conversation's last-known set, plus the selection notes that produced it.
  typealias CachedResult = (
    frames: [ConversationScreenFrame], banner: ConversationScreenFrame?, diagnostics: [String]
  )

  private static var cache: [String: CachedResult] = [:]

  /// Work already running for a conversation, shared across store instances.
  ///
  /// **The per-instance `task` guard is not enough.** Opening a note can build the detail view more
  /// than once in quick succession, and each rebuild brings a fresh `@StateObject` — so the guard
  /// sees `nil` every time and the whole pipeline runs twice. Measured: two adjudications 0.9s
  /// apart for one conversation, which is double the cost, double the latency, and twice as many
  /// candidates uploaded for no gain. Keying in-flight work by conversation instead of by instance
  /// means the second view awaits the first result rather than repeating it.
  private static var inFlight: [String: Task<Void, Never>] = [:]

  /// Forget the session cache, as an app relaunch does, so a test can prove the persisted set is
  /// what a later note reads.
  static func resetSessionCacheForTesting() {
    cache.removeAll()
  }

  private var conversationID = ""
  private var cacheKey = ""
  private var selectionWindow: MeetingScreenshotSelectionWindow?
  private var task: Task<Void, Never>?
  private let featureEnabled: () -> Bool
  private let selectCandidates: (MeetingScreenshotSelectionWindow) async -> MeetingFrameSelector.Outcome
  private let captureAuthorization: () -> MeetingEvidenceAuthorization?
  private let adjudicateAndCommit:
    @Sendable ([MeetingFrameCandidate], String, MeetingEvidenceAuthorization) async throws
      -> ConversationScreenFrameSet
  private let fetchPersistedSet: @Sendable (String) async throws -> ConversationScreenFrameSet
  private let deleteFrameRemote: @Sendable (String, String) async throws -> Void
  private let sealActiveRecording: @Sendable () async -> Void
  private let now: @Sendable () -> Date
  private var isRefreshingAfterUnavailableContent = false

  /// A cached set whose signed URLs expire within this margin is refetched rather than rendered.
  /// The finalization pass fills the cache long before a note is opened, and the server reports
  /// each signature's true remaining lifetime, which can be well under an hour.
  nonisolated static let signedURLRefreshMargin: TimeInterval = 5 * 60

  /// Whether every signed URL in a cached result outlives `now` by the refresh margin.
  nonisolated static func signedURLsAreFresh(
    frames: [ConversationScreenFrame], banner: ConversationScreenFrame?, now: Date
  ) -> Bool {
    (frames + (banner.map { [$0] } ?? [])).allSatisfy {
      $0.urlExpiresAt.timeIntervalSince(now) > signedURLRefreshMargin
    }
  }

  /// Phase detail when the meeting's last frames are still in Rewind's unsealed chunk and sealing
  /// it did not release them. Not cached and nothing uploaded, so the next load selects again.
  nonisolated static let activeChunkRetryDetail = "meeting frames still being recorded"
  /// Phase detail when the local Rewind store could not be read at all.
  nonisolated static let screenHistoryUnavailableDetail = "screen history unavailable"
  /// Phase detail when no owner could be bound, or the owner changed before the upload.
  nonisolated static let ownerChangedDetail = "signed-in account changed"

  /// A bounded phase detail: an owner change keeps its own label so telemetry can bucket it.
  nonisolated static func failureDetail(_ error: Error) -> String {
    if error is MeetingEvidenceAuthorizationError { return ownerChangedDetail }
    if case AuthError.userChangedDuringRequest = error { return ownerChangedDetail }
    return error.localizedDescription
  }

  init(
    captureAuthorization: @escaping () -> MeetingEvidenceAuthorization? = {
      MeetingEvidenceAuthorization.captureCurrentOwner()
    },
    featureEnabled: @escaping () -> Bool = { MeetingNoteScreenshotsFeature.isEnabled },
    selectCandidates: @escaping (MeetingScreenshotSelectionWindow) async -> MeetingFrameSelector.Outcome = {
      await MeetingFrameSelector.selectCandidates(in: $0)
    },
    adjudicateAndCommit:
      @escaping @Sendable (
        [MeetingFrameCandidate], String, MeetingEvidenceAuthorization
      ) async throws -> ConversationScreenFrameSet = {
        try await MeetingFrameJudge.shared.adjudicateAndCommit(candidates: $0, subjectID: $1, authorization: $2)
      },
    fetchPersistedSet: @escaping @Sendable (String) async throws -> ConversationScreenFrameSet = {
      try await APIClient.shared.getConversationScreenFrames(conversationID: $0)
    },
    deleteFrameRemote: @escaping @Sendable (String, String) async throws -> Void = {
      try await APIClient.shared.deleteConversationScreenFrame(conversationID: $0, frameID: $1)
    },
    now: @escaping @Sendable () -> Date = { Date() },
    sealActiveRecording: @escaping @Sendable () async -> Void = {
      // The same finalize-and-continue flush Rewind uses for power and memory transitions; the
      // next captured frame opens a fresh chunk.
      _ = try? await RewindStorage.shared.flushCurrentVideoChunk()
    }
  ) {
    self.captureAuthorization = captureAuthorization
    self.sealActiveRecording = sealActiveRecording
    self.now = now
    self.featureEnabled = featureEnabled
    self.selectCandidates = selectCandidates
    self.adjudicateAndCommit = adjudicateAndCommit
    self.fetchPersistedSet = fetchPersistedSet
    self.deleteFrameRemote = deleteFrameRemote
  }

  deinit { task?.cancel() }

  static var isEnabled: Bool { MeetingNoteScreenshotsFeature.isEnabled }

  /// Record the run's explanation and put it where a developer can actually read it.
  private func publish(notes: [String]) {
    diagnostics = notes
    for note in notes {
      log("MeetingScreenshots: · \(note)")
    }
  }

  func load(conversationID: String, selectionWindow: MeetingScreenshotSelectionWindow?) {
    guard featureEnabled() else {
      phase = .disabled
      return
    }
    guard let selectionWindow else {
      self.conversationID = conversationID
      self.selectionWindow = nil
      cacheKey = "\(conversationID):untrusted"
      task?.cancel()
      task = nil
      frames = []
      banner = nil
      publish(notes: ["no trustworthy transcript content window; screenshots hidden"])
      phase = .noCapture
      return
    }
    let requestedCacheKey = "\(conversationID):\(selectionWindow.fingerprint)"
    guard self.conversationID.isEmpty || self.conversationID == conversationID else { return }
    if task != nil {
      guard cacheKey != requestedCacheKey else { return }
      // Detail hydration can replace an omitted/untrusted transcript with a trusted window while
      // selection is in flight. Fence the old result and immediately start the newly trusted run.
      self.selectionWindow = selectionWindow
      task?.cancel()
      task = nil
    }
    self.conversationID = conversationID
    self.selectionWindow = selectionWindow
    cacheKey = requestedCacheKey
    log(
      "MeetingScreenshots: load requested for \(conversationID), selection "
        + selectionWindow.fingerprint)
    if let hit = Self.cache[requestedCacheKey],
      !Self.signedURLsAreFresh(frames: hit.frames, banner: hit.banner, now: now())
    {
      // Expired or about to: drop it, and let the run below re-read the persisted set (it is the
      // server's `GET`, and it only re-selects if that set was judged for a different window).
      log("MeetingScreenshots: cached signed URLs for \(conversationID) expired; refetching")
      Self.cache[requestedCacheKey] = nil
    }
    if let hit = Self.cache[requestedCacheKey] {
      frames = hit.frames
      banner = hit.banner
      diagnostics = hit.diagnostics
      phase = (hit.frames.isEmpty && hit.banner == nil) ? .noCapture : .ready
      return
    }

    if let existing = Self.inFlight[requestedCacheKey] {
      // Someone else is already doing this. Wait for them, then read what they cached.
      task = Task { [weak self] in
        _ = await existing.value
        guard let self, self.cacheKey == requestedCacheKey else { return }
        self.adopt(cached: Self.cache[requestedCacheKey])
        self.task = nil
      }
      return
    }

    let work = Task { [weak self] in
      guard let self else { return }
      await self.run(selectionWindow: selectionWindow)
    }
    Self.inFlight[requestedCacheKey] = work
    task = Task { [weak self] in
      _ = await work.value
      Self.inFlight[requestedCacheKey] = nil
      if self?.cacheKey == requestedCacheKey {
        self?.task = nil
      }
    }
  }

  /// `load`, then wait for it to settle. The finalization pass uses this so the one run it starts
  /// is the same shared, de-duplicated run a note opened mid-flight joins, and its result lands in
  /// the same session cache the note reads.
  @discardableResult
  func loadAndWait(conversationID: String, selectionWindow: MeetingScreenshotSelectionWindow) async -> Phase {
    load(conversationID: conversationID, selectionWindow: selectionWindow)
    if let task { await task.value }
    return phase
  }

  // MARK: - Full size

  /// Every frame this note can show full-size, banner included, in reading order.
  private var expandable: [ConversationScreenFrame] {
    (banner.map { [$0] } ?? []) + frames
  }

  /// The whole set, ready to hand to Quick Look.
  ///
  /// The *set* and not the one frame that was clicked, because Quick Look's own left/right
  /// stepping walks whatever it was given — so handing it everything is what makes arrowing
  /// through a meeting work without a stepper of ours in the middle of it. A frame whose
  /// `content_url` does not parse drops out here rather than becoming a panel that opens onto
  /// nothing.
  var quickLookFrames: [QuickLookFrame] {
    expandable.compactMap { QuickLookFrame(frame: $0) }
  }

  // MARK: - Refresh and delete

  /// Re-fetch the persisted set from the server. Used both after a delete — the server may have
  /// promoted another already-persisted frame to banner, and this is how the client finds out,
  /// since it never decides that itself — and to recover from an expired signed URL rather than
  /// leave a broken image on screen (`url_expires_at` is 60 minutes).
  func refreshPersistedSet() async {
    guard !conversationID.isEmpty, let selectionWindow else { return }
    do {
      let set = try await fetchPersistedSet(conversationID)
      apply(frameSet: set, within: selectionWindow, notes: diagnostics)
    } catch {
      log("MeetingScreenshots: refresh failed for \(conversationID) — \(error.localizedDescription)")
      // Leave whatever is currently displayed in place. A transient refresh failure must not
      // blank out screenshots that were already showing correctly.
    }
  }

  /// A thumbnail failed to load — most often an expired signature. Every visible tile may report at
  /// once, so concurrent reports coalesce into one refetch.
  func refreshAfterContentUnavailable() async {
    guard !isRefreshingAfterUnavailableContent else { return }
    isRefreshingAfterUnavailableContent = true
    defer { isRefreshingAfterUnavailableContent = false }
    await refreshPersistedSet()
  }

  /// Delete one persisted frame. The caller (the lightbox) confirms the destructive action before
  /// this runs. What happens to the banner afterward is the server's call, not this method's — it
  /// only re-reads whatever set comes back.
  func deleteFrame(frameID: String) async {
    guard !conversationID.isEmpty else { return }
    do {
      try await deleteFrameRemote(conversationID, frameID)
      await refreshPersistedSet()
    } catch {
      log(
        "MeetingScreenshots: delete failed for \(frameID) in \(conversationID) — "
          + error.localizedDescription)
    }
  }

  // MARK: - Run

  /// Take the result another instance already computed.
  private func adopt(cached: CachedResult?) {
    guard let cached else { return }
    frames = cached.frames
    banner = cached.banner
    diagnostics = cached.diagnostics
    phase = cached.frames.isEmpty && cached.banner == nil ? .noCapture : .ready
  }

  private func apply(
    frameSet: ConversationScreenFrameSet,
    within selectionWindow: MeetingScreenshotSelectionWindow,
    notes: [String]
  ) {
    frames = frameSet.strip.filter { selectionWindow.contains($0.capturedAt) }
    banner = frameSet.banner.flatMap { selectionWindow.contains($0.capturedAt) ? $0 : nil }
    log(
      "MeetingScreenshots: trusted set has \(frames.count) strip frame(s), banner="
        + "\(banner?.id ?? "none")")
    publish(notes: notes)
    phase = (frames.isEmpty && banner == nil) ? .noCapture : .ready
    Self.cache[cacheKey] = (frames, banner, notes)
  }

  private func run(selectionWindow: MeetingScreenshotSelectionWindow) async {
    // Ask the server what it already knows before offering it anything. `GET` is the source of
    // truth for what this conversation currently shows (contract §1).
    //
    // The test is `adjudicatedAt`, deliberately not `revision`. `revision` is a monotonic
    // mutation counter over this conversation's persisted frame set, and it only moves when a
    // frame was actually approved and persisted, so a pass that judged every candidate and
    // rejected all of them leaves it at 0 — identical to a conversation nobody has ever tried.
    // Keying off it would mean re-selecting and re-uploading on every reopen, and the frames
    // re-uploaded would be exactly the ones the judge refused: the credentials, the DM window,
    // the inbox. A privacy gate that re-ships its own rejects on a loop is worse than no gate,
    // so the server stamps `screen_frames_adjudicated_at` whatever it decided, and this asks
    // that instead.
    //
    // `revision` is still what tells the *view* something changed; it is a mutation counter,
    // not a record of having asked.
    if let existing = try? await fetchPersistedSet(conversationID), existing.adjudicatedAt != nil,
      existing.selectionFingerprint == selectionWindow.fingerprint
    {
      guard self.selectionWindow == selectionWindow else { return }
      log("MeetingScreenshots: loaded existing revision \(existing.revision) for \(conversationID)")
      apply(
        frameSet: existing,
        within: selectionWindow,
        notes: ["loaded screenshots selected for this transcript content window"])
      return
    }

    // Bind this run to one owner before reading any of that owner's screen history. Every upload
    // below re-checks it and carries it into transport auth.
    guard let authorization = captureAuthorization() else {
      log("MeetingScreenshots: no signed-in owner to bind for \(conversationID); not selecting")
      phase = .failed(Self.ownerChangedDetail)
      return
    }
    phase = .selecting
    log(
      "MeetingScreenshots: selecting for \(conversationID) trusted window "
        + "\(selectionWindow.start) -> \(selectionWindow.end)")

    var outcome = await selectCandidates(selectionWindow)
    guard self.selectionWindow == selectionWindow else { return }
    if outcome.drops[MeetingFrameSelector.activeChunkDropReason, default: 0] > 0 {
      // The end of the meeting is still in the chunk being written. Seal it and select once more,
      // rather than judge — and have the server stamp as final — a set missing the last minute.
      await sealActiveRecording()
      outcome = await selectCandidates(selectionWindow)
      guard self.selectionWindow == selectionWindow else { return }
      if outcome.drops[MeetingFrameSelector.activeChunkDropReason, default: 0] > 0 {
        log("MeetingScreenshots: active chunk still unsealed for \(conversationID); will retry")
        publish(notes: ["the meeting's last frames are still being recorded"])
        phase = .failed(Self.activeChunkRetryDetail)
        return
      }
    }
    var notes: [String] = []
    notes.append("\(outcome.framesInWindow) frame(s) captured during this conversation")
    for (reason, count) in outcome.drops.sorted(by: { $0.value > $1.value }) {
      notes.append("dropped \(count): \(reason)")
    }
    notes.append("\(outcome.candidates.count) candidate(s) selected for upload")
    log(
      "MeetingScreenshots: \(outcome.framesInWindow) frame(s) in window, "
        + "\(outcome.candidates.count) candidate(s), drops=\(outcome.drops)")

    guard authorization.isCurrent else {
      // What was just read belongs to an owner who is no longer signed in: upload none of it.
      log("MeetingScreenshots: signed-in account changed during selection for \(conversationID)")
      publish(notes: ["the signed-in account changed"])
      phase = .failed(Self.ownerChangedDetail)
      return
    }

    if outcome.localReadFailed {
      // Could not look is not "found nothing": never stamp it as final. Uncached, so the next load
      // (or the post-finalize retry) selects again; the server's bounded wait covers the notes.
      log("MeetingScreenshots: screen history unavailable for \(conversationID); will retry")
      publish(notes: ["screen history could not be read"])
      phase = .failed(Self.screenHistoryUnavailableDetail)
      return
    }

    guard !outcome.candidates.isEmpty else {
      // Nothing to offer, but the pass is done: send the empty stamp (no bytes, no judging). It is
      // what the backend's notes admission waits for, and it records this window as looked at.
      do {
        let stamped = try await adjudicateAndCommit([], conversationID, authorization)
        guard self.selectionWindow == selectionWindow else { return }
        apply(frameSet: stamped, within: selectionWindow, notes: notes)
      } catch {
        guard self.selectionWindow == selectionWindow else { return }
        log("MeetingScreenshots: empty evidence stamp failed for \(conversationID) — \(error.localizedDescription)")
        // Uncached failure, like any other adjudication failure: the retry and the next open
        // must be able to stamp again, and the pass records the degraded fallback.
        publish(notes: notes)
        phase = .failed(Self.failureDetail(error))
      }
      return
    }

    phase = .judging(candidates: outcome.candidates.count)

    let frameSet: ConversationScreenFrameSet
    do {
      frameSet = try await adjudicateAndCommit(outcome.candidates, conversationID, authorization)
    } catch {
      guard self.selectionWindow == selectionWindow else { return }
      // No network, a 4xx/5xx, a timeout — all of it fails the same way: the view for `.failed`
      // renders nothing, never an error card, so an unprovisioned or unreachable backend simply
      // looks like a note with no screenshots.
      log("MeetingScreenshots: adjudication failed for \(conversationID) — \(error.localizedDescription)")
      publish(notes: notes)
      phase = .failed(Self.failureDetail(error))
      return
    }

    guard self.selectionWindow == selectionWindow else { return }
    apply(frameSet: frameSet, within: selectionWindow, notes: notes)
  }
}
