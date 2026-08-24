//
//  MeetingScreenshotsStore.swift — one conversation's pictures, and the state of getting them.
//
//  **Prototype scope, stated once so nothing downstream has to guess:** nothing here uploads,
//  stores, or shares anything. Frames are read from the local Rewind store and drawn from local
//  pixels. The adjudication call is the only thing that leaves the machine, and it carries frames
//  the deterministic filter already admitted. The shipping design's server half — canonical bytes,
//  signed approvals, GCS objects, the attach route, deletion closure — is not implemented, so what
//  this bundle tests is *selection quality and how the note looks*, which is the part that could
//  not be settled on paper.
//
//  The store is per-conversation and lives as long as the detail view. Results are memoised for the
//  session so reopening a note does not re-judge it.
//

import Foundation
import SwiftUI

/// Developer-only gate for the local meeting-screenshot prototype.
///
/// The only adjudicator implemented in this change is a manually launched loopback sidecar. Keep
/// every distributed bundle dark even if its process environment is contaminated, and require an
/// explicit opt-in on local development bundles.
enum MeetingNoteScreenshotsFeature {
  static let localOverrideName = "OMI_FORCE_MEETING_NOTE_SCREENSHOTS"

  static var isEnabled: Bool {
    isEnabled(
      allowsLocalAutomation: AppBuild.allowsLocalAutomation,
      localOverrideValue: ProcessInfo.processInfo.environment[localOverrideName])
  }

  static func isEnabled(allowsLocalAutomation: Bool, localOverrideValue: String?) -> Bool {
    allowsLocalAutomation && localOverrideValue == "1"
  }
}

@MainActor
final class MeetingScreenshotsStore: ObservableObject {

  enum Phase: Equatable {
    case idle
    case disabled
    /// Rewind has no frames inside this conversation's window. Common and not an error.
    case noCapture
    case selecting
    case judging(candidates: Int)
    case ready
    case failed(String)
  }

  struct Frame: Identifiable, Equatable {
    let moment: SpineMoment
    let caption: String
    let labels: [String]
    var id: Int64 { moment.id }
  }

  @Published private(set) var phase: Phase = .idle
  @Published private(set) var frames: [Frame] = []
  @Published private(set) var banner: Frame?
  /// What the deterministic filter and the enforcement layer did, in the user's words.
  ///
  /// **Nothing renders this yet, deliberately.** The shipping design has a "how these were
  /// chosen" disclosure; this change is dark, so there is no surface to put one on. Keeping the
  /// record and writing it to the log is what makes the gate auditable in the only place a
  /// developer can look today — a gate whose corrections are invisible is a gate that looks like
  /// it is not needed. It stays `@Published` so the eventual disclosure needs no plumbing, not
  /// because a view reads it.
  @Published private(set) var diagnostics: [String] = []

  private static var cache: [String: (frames: [Frame], banner: Frame?, diagnostics: [String])] = [:]

  /// Work already running for a conversation, shared across store instances.
  ///
  /// **The per-instance `task` guard is not enough.** Opening a note can build the detail view more
  /// than once in quick succession, and each rebuild brings a fresh `@StateObject` — so the guard
  /// sees `nil` every time and the whole pipeline runs twice. Measured: two adjudications 0.9s
  /// apart for one conversation, which is double the cost, double the latency, and twice as many
  /// frames shown to the judge for no gain. Keying in-flight work by conversation instead of by
  /// instance means the second view awaits the first result rather than repeating it.
  private static var inFlight: [String: Task<Void, Never>] = [:]

  private var conversationID = ""
  private var task: Task<Void, Never>?
  private let featureEnabled: () -> Bool
  private let selectCandidates: (Date, Date) async -> MeetingFrameSelector.Outcome

  init(
    featureEnabled: @escaping () -> Bool = { MeetingNoteScreenshotsFeature.isEnabled },
    selectCandidates: @escaping (Date, Date) async -> MeetingFrameSelector.Outcome = {
      await MeetingFrameSelector.selectCandidates(from: $0, to: $1)
    }
  ) {
    self.featureEnabled = featureEnabled
    self.selectCandidates = selectCandidates
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

  func load(conversationID: String, title: String, start: Date, end: Date) {
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
      phase = hit.frames.isEmpty ? .noCapture : .ready
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
      await self.run(title: title, start: start, end: end)
    }
    Self.inFlight[conversationID] = work
    task = Task { [weak self] in
      _ = await work.value
      Self.inFlight[conversationID] = nil
      self?.task = nil
    }
  }

  // MARK: - Lightbox

  /// Every frame this note can show full-size, banner included, in reading order.
  private var expandable: [Frame] {
    (banner.map { [$0] } ?? []) + frames
  }

  /// The frame behind a tile, ready to hand to the shared lightbox.
  func lightboxItem(for id: Int64) -> ScreenFrameLightboxItem? {
    guard let frame = expandable.first(where: { $0.id == id }) else { return nil }
    return ScreenFrameLightboxItem(screenshot: frame.moment.screenshot, caption: frame.caption)
  }

  /// The next frame along, wrapping at both ends so arrow keys never dead-end.
  func lightboxItem(steppingFrom id: Int64?, by step: Int) -> ScreenFrameLightboxItem? {
    let all = expandable
    guard !all.isEmpty else { return nil }
    guard let id, let current = all.firstIndex(where: { $0.id == id }) else {
      return lightboxItem(for: all[0].id)
    }
    let next = ((current + step) % all.count + all.count) % all.count
    return lightboxItem(for: all[next].id)
  }

  /// Take the result another instance already computed.
  private func adopt(cached: (frames: [Frame], banner: Frame?, diagnostics: [String])?) {
    guard let cached else { return }
    frames = cached.frames
    banner = cached.banner
    diagnostics = cached.diagnostics
    phase = cached.frames.isEmpty && cached.banner == nil ? .noCapture : .ready
  }

  private func run(title: String, start: Date, end: Date) async {
    phase = .selecting
    log("MeetingScreenshots: selecting for \(conversationID) window \(start) -> \(end)")

    let outcome = await selectCandidates(start, end)
    var notes: [String] = []
    notes.append("\(outcome.framesInWindow) frame(s) captured during this conversation")
    for (reason, count) in outcome.drops.sorted(by: { $0.value > $1.value }) {
      notes.append("dropped \(count): \(reason)")
    }
    notes.append("\(outcome.candidates.count) candidate(s) shown to the judge")
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

    let adjudication: MeetingFrameAdjudication
    do {
      adjudication = try await MeetingFrameJudge.shared.adjudicate(
        candidates: outcome.candidates, meetingTitle: title)
    } catch {
      log("MeetingScreenshots: adjudication failed — \(error.localizedDescription)")
      publish(notes: notes)
      phase = .failed(error.localizedDescription)
      return
    }

    notes.append("the judge published \(adjudication.modelPublishedCount)")
    notes.append(contentsOf: adjudication.corrections.map { "enforcement: \($0)" })

    var byID: [Int64: MeetingFrameCandidate] = [:]
    for candidate in outcome.candidates {
      byID[candidate.id] = candidate
    }
    let published: [Frame] = adjudication.published.compactMap { verdict in
      guard let candidate = byID[verdict.frameID] else { return nil }
      return Frame(moment: candidate.moment, caption: verdict.caption, labels: verdict.labels)
    }

    let bannerFrame = adjudication.bannerFrameID.flatMap { id in
      published.first { $0.id == id }
    }
    // The banner is not also a strip tile — showing the same picture twice in one note reads as a
    // bug, and the strip is evidence the banner is not.
    let strip = published.filter { $0.id != bannerFrame?.id }

    log(
      "MeetingScreenshots: published \(published.count) — banner="
        + "\(bannerFrame.map { String($0.id) } ?? "none"), strip=\(strip.count)")
    frames = strip
    banner = bannerFrame
    publish(notes: notes)
    phase = published.isEmpty ? .noCapture : .ready
    Self.cache[conversationID] = (strip, bannerFrame, notes)
  }
}
