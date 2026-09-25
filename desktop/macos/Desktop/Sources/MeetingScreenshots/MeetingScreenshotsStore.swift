//
//  MeetingScreenshotsStore.swift — one conversation's pictures, and the state of getting them.
//
//  The server is the source of truth for everything past selection: what got approved, the cap,
//  the banner, deletion, promotion after a delete. This store's job is narrower than it looks —
//  run on-device selection, hand the survivors to `MeetingFrameJudge`, and render exactly the
//  `ConversationScreenFrameSet` the server returns. It never re-derives a verdict from what comes
//  back, and every failure path (no network, 4xx/5xx, an empty set) collapses to the same `.failed`
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

  private var conversationID = ""
  private var task: Task<Void, Never>?
  private let featureEnabled: () -> Bool
  private let selectCandidates: (Date, Date) async -> MeetingFrameSelector.Outcome
  private let adjudicateAndCommit:
    @Sendable ([MeetingFrameCandidate], String) async throws -> ConversationScreenFrameSet
  private let fetchPersistedSet: @Sendable (String) async throws -> ConversationScreenFrameSet
  private let deleteFrameRemote: @Sendable (String, String) async throws -> Void

  init(
    featureEnabled: @escaping () -> Bool = { MeetingNoteScreenshotsFeature.isEnabled },
    selectCandidates: @escaping (Date, Date) async -> MeetingFrameSelector.Outcome = {
      await MeetingFrameSelector.selectCandidates(from: $0, to: $1)
    },
    adjudicateAndCommit:
      @escaping @Sendable (
        [MeetingFrameCandidate], String
      ) async throws -> ConversationScreenFrameSet = {
        try await MeetingFrameJudge.shared.adjudicateAndCommit(candidates: $0, subjectID: $1)
      },
    fetchPersistedSet: @escaping @Sendable (String) async throws -> ConversationScreenFrameSet = {
      try await APIClient.shared.getConversationScreenFrames(conversationID: $0)
    },
    deleteFrameRemote: @escaping @Sendable (String, String) async throws -> Void = {
      try await APIClient.shared.deleteConversationScreenFrame(conversationID: $0, frameID: $1)
    }
  ) {
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

  func load(conversationID: String, start: Date, end: Date) {
    guard featureEnabled() else {
      phase = .disabled
      return
    }
    guard task == nil, self.conversationID.isEmpty || self.conversationID == conversationID else { return }
    self.conversationID = conversationID
    log("MeetingScreenshots: load requested for \(conversationID)")
    if let hit = Self.cache[conversationID] {
      frames = hit.frames
      banner = hit.banner
      diagnostics = hit.diagnostics
      phase = (hit.frames.isEmpty && hit.banner == nil) ? .noCapture : .ready
      return
    }

    if let existing = Self.inFlight[conversationID] {
      // Someone else is already doing this. Wait for them, then read what they cached.
      task = Task { [weak self] in
        _ = await existing.value
        guard let self else { return }
        self.adopt(cached: Self.cache[conversationID])
        self.task = nil
      }
      return
    }

    let work = Task { [weak self] in
      guard let self else { return }
      await self.run(start: start, end: end)
    }
    Self.inFlight[conversationID] = work
    task = Task { [weak self] in
      _ = await work.value
      Self.inFlight[conversationID] = nil
      self?.task = nil
    }
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
    guard !conversationID.isEmpty else { return }
    do {
      let set = try await fetchPersistedSet(conversationID)
      apply(frameSet: set, notes: diagnostics)
    } catch {
      log("MeetingScreenshots: refresh failed for \(conversationID) — \(error.localizedDescription)")
      // Leave whatever is currently displayed in place. A transient refresh failure must not
      // blank out screenshots that were already showing correctly.
    }
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

  private func apply(frameSet: ConversationScreenFrameSet, notes: [String]) {
    frames = frameSet.strip
    banner = frameSet.banner
    log(
      "MeetingScreenshots: set has \(frameSet.strip.count) strip frame(s), banner="
        + "\(frameSet.banner?.id ?? "none")")
    publish(notes: notes)
    phase = frameSet.isEmpty ? .noCapture : .ready
    Self.cache[conversationID] = (frameSet.strip, frameSet.banner, notes)
  }

  private func run(start: Date, end: Date) async {
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
    if let existing = try? await fetchPersistedSet(conversationID), existing.adjudicatedAt != nil {
      log("MeetingScreenshots: loaded existing revision \(existing.revision) for \(conversationID)")
      apply(frameSet: existing, notes: ["loaded this conversation's existing screenshots"])
      return
    }

    phase = .selecting
    log("MeetingScreenshots: selecting for \(conversationID) window \(start) -> \(end)")

    let outcome = await selectCandidates(start, end)
    var notes: [String] = []
    notes.append("\(outcome.framesInWindow) frame(s) captured during this conversation")
    for (reason, count) in outcome.drops.sorted(by: { $0.value > $1.value }) {
      notes.append("dropped \(count): \(reason)")
    }
    notes.append("\(outcome.candidates.count) candidate(s) selected for upload")
    log(
      "MeetingScreenshots: \(outcome.framesInWindow) frame(s) in window, "
        + "\(outcome.candidates.count) candidate(s), drops=\(outcome.drops)")

    guard !outcome.candidates.isEmpty else {
      publish(notes: notes)
      phase = .noCapture
      Self.cache[conversationID] = ([], nil, notes)
      return
    }

    phase = .judging(candidates: outcome.candidates.count)

    let frameSet: ConversationScreenFrameSet
    do {
      frameSet = try await adjudicateAndCommit(outcome.candidates, conversationID)
    } catch {
      // No network, a 4xx/5xx, a timeout — all of it fails the same way: the view for `.failed`
      // renders nothing, never an error card, so an unprovisioned or unreachable backend simply
      // looks like a note with no screenshots.
      log("MeetingScreenshots: adjudication failed for \(conversationID) — \(error.localizedDescription)")
      publish(notes: notes)
      phase = .failed(error.localizedDescription)
      return
    }

    apply(frameSet: frameSet, notes: notes)
  }
}
