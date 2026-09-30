//
//  MeetingFrameSelector.swift — which frames from a meeting are even worth showing a judge.
//
//  This is the deterministic half of the screenshot gate, and it runs entirely on-device. It never
//  makes a network call and it never decides that anything may be *uploaded*; it only narrows a
//  meeting's worth of capture down to a bounded candidate set. The judge decides publication.
//
//  Three things in here were measured rather than guessed, on a real 2,061-frame local store
//  (`omi-knowledge:projects/meeting-summary-reliability/evidence/2026-08-20-meeting-note-screenshots-selection-measurements.md`):
//
//  - **Bucket compaction does nearly all the reduction, for free.** 53–144 frames per meeting
//    collapse to 6–25 candidates on `(app, window, bucket)` alone, before any model runs.
//  - **Near-duplicates survive bucket compaction and reach the published set in every meeting.**
//    Two frames of the *same screen* were published in one six-picture strip at 0.96 OCR
//    similarity. Cross-bucket suppression is not an optimisation; it is what stops the strip
//    repeating itself.
//  - **OCR absence is a scheduler artifact, not an empty screen.** 70% of frames carry under 40
//    characters of OCR, and 79% of those sit within 60s of a *rich*-OCR frame of the same app and
//    window. So a filter keyed on OCR length silently discards most of the corpus for a reason
//    unrelated to what was on screen. Frames without usable OCR are therefore compared by
//    perceptual hash instead of being dropped, and "no OCR" means *unknown*, never *empty*.
//

import Foundation
import GRDB

/// The wall-clock interval in which a conversation is known to contain transcript content.
///
/// `started_at...finished_at` is a capture lifecycle envelope, not a content interval: legacy
/// listen conversations can retain an early socket origin across a rollover. Transcript offsets
/// are only projected onto that origin when the origin is independently trustworthy (desktop
/// `/from-segments`, audio-timeline v2) or when the projection agrees with `finished_at`.
///
/// The server recomputes this window (`routers/screen_frames.py` `_trusted_content_window`) and
/// stamps its fingerprint on the adjudicated set. The two must agree to the millisecond, or a note
/// opened after finalization re-selects and re-uploads a set the server already judged. So the
/// arithmetic here follows the server's exactly: microsecond origin, offsets rounded to whole
/// microseconds half-to-even (`timedelta(seconds=)`), and milliseconds rounded half-to-even
/// (`round(dt.timestamp() * 1000)`). The tolerance is the server's too.
struct MeetingScreenshotSelectionWindow: Equatable, Sendable {
  static let policy = "meeting-content-v1"
  /// `LEGACY_CONTENT_WINDOW_TOLERANCE_SECONDS`. A looser client bound trusts windows the server
  /// does not, and the server then stamps its legacy fingerprint, which never matches.
  static let legacyConsistencyTolerance: TimeInterval = 30

  let start: Date
  let end: Date
  /// The server's own fingerprint, verbatim, when the window was read from it rather than derived.
  private var serverFingerprint: String?

  init(start: Date, end: Date) {
    self.start = start
    self.end = end
  }

  /// The window the server reports as `trusted_selection_fingerprint`. Its milliseconds are
  /// rounded, so selection runs 1 ms inside them: a frame that rounding placed on the boundary
  /// could fall a fraction of a millisecond outside the server's exact window, and one frame
  /// outside rejects the whole adjudication request. The fingerprint itself is kept verbatim.
  init?(serverFingerprint: String) {
    let parts = serverFingerprint.split(separator: ":")
    guard parts.count == 3, parts[0] == Self.policy, let startMs = Int64(parts[1]), let endMs = Int64(parts[2]),
      endMs - startMs > 2
    else { return nil }
    start = Date(timeIntervalSince1970: Double(startMs + 1) / 1_000)
    end = Date(timeIntervalSince1970: Double(endMs - 1) / 1_000)
    self.serverFingerprint = serverFingerprint
  }

  var fingerprint: String {
    serverFingerprint ?? "\(Self.policy):\(Self.serverMilliseconds(start)):\(Self.serverMilliseconds(end))"
  }

  /// `round(datetime.timestamp() * 1000)` for a microsecond-precise instant.
  static func serverMilliseconds(_ date: Date) -> Int64 {
    let microseconds = (date.timeIntervalSince1970 * 1_000_000).rounded()
    return Int64((microseconds / 1_000_000 * 1_000).rounded(.toNearestOrEven))
  }

  /// `timedelta(seconds=value)` in whole microseconds.
  static func serverMicroseconds(offset value: Double) -> Int64 {
    let whole = value.rounded(.towardZero)
    return Int64(whole) * 1_000_000 + Int64(((value - whole) * 1_000_000).rounded(.toNearestOrEven))
  }

  func contains(_ date: Date) -> Bool { date >= start && date <= end }

  static func resolve(_ conversation: ServerConversation) -> Self? {
    // List projections may omit transcript_segments entirely. Wait for the detail response rather
    // than mistaking an incomplete projection for an empty or differently bounded transcript.
    guard conversation.transcriptSegmentsIncluded else { return nil }
    let spans = conversation.transcriptSegments.compactMap { segment -> (Double, Double)? in
      guard !segment.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
      return (segment.start, segment.end)
    }
    return resolve(
      startedAt: conversation.startedAt,
      finishedAt: conversation.finishedAt,
      segmentSpans: spans,
      hasTrustedOrigin: conversation.createdFromSegments || conversation.audioTimelineVersion == 2)
  }

  /// Pure policy entry point used by regression tests without constructing a complete conversation.
  static func resolve(
    startedAt: Date?,
    finishedAt: Date?,
    segmentSpans: [(Double, Double)],
    hasTrustedOrigin: Bool
  ) -> Self? {
    guard let startedAt else { return nil }
    let valid = segmentSpans.filter {
      $0.0.isFinite && $0.1.isFinite && $0.0 >= 0 && $0.1 > $0.0
    }
    guard let firstOffset = valid.map(\.0).min(), let lastOffset = valid.map(\.1).max() else {
      return nil
    }

    let originMicroseconds = Int64((startedAt.timeIntervalSince1970 * 1_000_000).rounded())
    let start = Date(
      timeIntervalSince1970: Double(originMicroseconds + serverMicroseconds(offset: firstOffset)) / 1_000_000)
    let end = Date(
      timeIntervalSince1970: Double(originMicroseconds + serverMicroseconds(offset: lastOffset)) / 1_000_000)
    if !hasTrustedOrigin {
      guard let finishedAt,
        abs(end.timeIntervalSince(finishedAt)) <= legacyConsistencyTolerance
      else { return nil }
    }
    return Self(start: start, end: end)
  }
}

// MARK: - Candidate

/// One frame that survived the deterministic filter. Deliberately the same seven columns
/// `SpineMoment` carries, plus the text the similarity pass needs, so a candidate can be handed
/// straight to the existing thumbnail loader without a second query.
struct MeetingFrameCandidate: Identifiable, Equatable, Sendable {
  let id: Int64
  let timestamp: Date
  let appName: String
  let windowTitle: String?
  let imagePath: String?
  let videoChunkPath: String?
  let frameOffset: Int?
  let ocrText: String?

  var moment: SpineMoment {
    SpineMoment(
      id: id,
      timestamp: timestamp,
      appName: appName,
      windowTitle: windowTitle,
      imagePath: imagePath,
      videoChunkPath: videoChunkPath,
      frameOffset: frameOffset)
  }

  /// Whether this frame's OCR is rich enough for text similarity to mean anything.
  var hasUsableText: Bool { (ocrText?.count ?? 0) >= MeetingFrameSelector.usableOCRLength }
}

// MARK: - Policy

/// Apps whose frames may never become a candidate, whatever any model later thinks of them.
///
/// **This list is the load-bearing privacy layer, not the model.** The judge is a second opinion:
/// in the measured control it published frames it had itself labelled sensitive, so it cannot be
/// the only thing standing between a password manager and a note.
enum MeetingFrameDenylist {
  static let apps: Set<String> = [
    "1Password", "1Password 7", "1Password 8", "Keychain Access", "Bitwarden", "Dashlane",
    "LastPass", "Enpass", "KeePassXC",
    "Messages", "Signal", "WhatsApp", "Telegram", "Discord", "Slack",
    "Mail", "Spark", "Superhuman", "Outlook", "Microsoft Outlook",
    "Venmo", "Coinbase", "Robinhood",
  ]

  /// Window titles that disqualify a frame regardless of which app drew them.
  static let titlePatterns: [String] = [
    "password", "passphrase", "secret", "api key", "api_key", "private key", "seed phrase",
    "two-factor", "2fa", "one-time code", "credit card", "social security", "bank",
  ]

  static func excludes(app: String, windowTitle: String?) -> Bool {
    if apps.contains(app) { return true }
    guard let title = windowTitle?.lowercased(), !title.isEmpty else { return false }
    return titlePatterns.contains { title.contains($0) }
  }
}

// MARK: - Selector

enum MeetingFrameSelector {
  /// Below this many characters, OCR is treated as *absent* rather than as *short*. Measured: the
  /// OCR scheduler simply does not run on most rows.
  static let usableOCRLength = 40

  /// How wide a compaction bucket is. Two minutes rather than the five the sync path uses: a
  /// meeting is an hour, not a day, and five-minute buckets left some meetings with six candidates
  /// to choose six pictures from — no choice at all.
  static let bucketSeconds: TimeInterval = 120

  /// Above this OCR-shingle similarity two frames are the same screen.
  static let textSimilarityCeiling = 0.5

  /// Above this share of matching perceptual-hash bits two frames are the same screen. Applies to
  /// the ~70% of frames OCR never ran on.
  static let imageSimilarityCeiling = 0.90

  /// The most candidates ever uploaded. A ceiling, not a target — and no longer a locally chosen
  /// number: the purpose registry's `max_candidates` for `meeting_note_v1` is 8 (contract §3), and
  /// the wire type enforces it too (`ScreenFrameAdjudicationRequest.candidates`, `max_length=8`).
  /// Kept equal here so nothing is silently trimmed a second time at the upload boundary.
  static let candidateCeiling = MeetingFrameJudge.maxCandidatesPerRequest

  /// The drop reason for frames in Rewind's active chunk. Unlike every other drop it is temporary:
  /// the chunk seals within about a minute, and those frames are usually the end of the meeting.
  static let activeChunkDropReason = "chunk still being written"

  struct Outcome: Sendable {
    var candidates: [MeetingFrameCandidate] = []
    var framesInWindow = 0
    /// Why frames were dropped, for the diagnostics surface. A gate nobody can see the workings of
    /// is a gate nobody can debug when it silently returns nothing.
    var drops: [String: Int] = [:]
    /// The local Rewind store could not be read (no pool yet, or the query failed). Distinct from
    /// an empty result: "found nothing" may be stamped as final, "could not look" never is.
    var localReadFailed = false

    static let unavailable: Outcome = {
      var outcome = Outcome()
      outcome.localReadFailed = true
      return outcome
    }()
  }

  /// Every frame captured inside a conversation's window, narrowed to a bounded candidate set.
  static func selectCandidates(from start: Date, to end: Date) async -> Outcome {
    guard end > start else { return Outcome() }
    guard let pool = await SpineScreenIndex.poolWhenReady() else { return .unavailable }

    // A frame in the chunk still being written has no moov atom yet and cannot be decoded.
    let unfinalizedChunk = await VideoChunkEncoder.shared.currentChunkPath

    let rows: [Row]
    do {
      rows = try await pool.read { db in
        try Row.fetchAll(
          db,
          sql: """
              SELECT id, timestamp, appName, windowTitle, imagePath, videoChunkPath,
                     frameOffset, ocrText
              FROM screenshots
              WHERE timestamp >= ? AND timestamp <= ?
              ORDER BY timestamp ASC
            """,
          arguments: [start, end])
      }
    } catch {
      return .unavailable
    }

    let frames = rows.compactMap { row -> MeetingFrameCandidate? in
      guard let id: Int64 = row["id"], let timestamp: Date = row["timestamp"] else { return nil }
      return MeetingFrameCandidate(
        id: id,
        timestamp: timestamp,
        appName: row["appName"] ?? "",
        windowTitle: row["windowTitle"],
        imagePath: row["imagePath"],
        videoChunkPath: row["videoChunkPath"],
        frameOffset: row["frameOffset"],
        ocrText: row["ocrText"])
    }

    return await selectCandidates(
      frames,
      from: start,
      to: end,
      unfinalizedChunk: unfinalizedChunk,
      perceptualHash: { await MeetingFrameSimilarity.perceptualHash(of: $0) })
  }

  static func selectCandidates(in window: MeetingScreenshotSelectionWindow) async -> Outcome {
    await selectCandidates(from: window.start, to: window.end)
  }

  /// The production filtering policy over already-read frames. Keeping the time boundary here as
  /// well as in the SQL query makes its inclusive semantics executable without a live Rewind store.
  static func selectCandidates(
    _ frames: [MeetingFrameCandidate],
    from start: Date,
    to end: Date,
    unfinalizedChunk: String? = nil,
    perceptualHash: (MeetingFrameCandidate) async -> UInt64? = {
      await MeetingFrameSimilarity.perceptualHash(of: $0)
    }
  ) async -> Outcome {
    guard end > start else { return Outcome() }

    let windowed = frames.filter { $0.timestamp >= start && $0.timestamp <= end }
    var outcome = Outcome()
    outcome.framesInWindow = windowed.count
    var kept: [MeetingFrameCandidate] = []

    for frame in windowed {
      if MeetingFrameDenylist.excludes(app: frame.appName, windowTitle: frame.windowTitle) {
        outcome.drops["denylisted", default: 0] += 1
        continue
      }
      if (frame.videoChunkPath?.isEmpty ?? true) && (frame.imagePath?.isEmpty ?? true) {
        outcome.drops["no pixels recorded", default: 0] += 1
        continue
      }
      if let chunk = frame.videoChunkPath, let unfinalizedChunk, chunk == unfinalizedChunk {
        outcome.drops[activeChunkDropReason, default: 0] += 1
        continue
      }
      kept.append(frame)
    }

    // One winner per (app, window, bucket). Richest OCR wins where there is any, otherwise the
    // middle of the bucket — the edges of a bucket catch transitions and half-drawn windows.
    var buckets: [String: [MeetingFrameCandidate]] = [:]
    for frame in kept {
      let bucket = Int(frame.timestamp.timeIntervalSince1970 / bucketSeconds)
      buckets["\(frame.appName)\u{1}\(frame.windowTitle ?? "")\u{1}\(bucket)", default: []].append(frame)
    }
    var winners: [MeetingFrameCandidate] = []
    for (_, group) in buckets {
      let richest = group.max(by: { ($0.ocrText?.count ?? 0) < ($1.ocrText?.count ?? 0) })
      let winner: MeetingFrameCandidate
      if let richest, richest.hasUsableText {
        winner = richest
      } else {
        winner = group[group.count / 2]
      }
      winners.append(winner)
      outcome.drops["same window, same minutes", default: 0] += group.count - 1
    }
    winners.sort { $0.timestamp < $1.timestamp }

    // Cross-bucket near-duplicate suppression. Text where there is text, pixels where there is not.
    var survivors: [MeetingFrameCandidate] = []
    var shingles: [Int64: Set<Int>] = [:]
    var hashes: [Int64: UInt64] = [:]
    for frame in winners {
      var duplicate = false
      if frame.hasUsableText {
        let mine = MeetingFrameSimilarity.shingles(frame.ocrText ?? "")
        shingles[frame.id] = mine
        for other in survivors where other.hasUsableText {
          guard let theirs = shingles[other.id] else { continue }
          if MeetingFrameSimilarity.jaccard(mine, theirs) >= textSimilarityCeiling {
            duplicate = true
            break
          }
        }
      } else if let mine = await perceptualHash(frame) {
        hashes[frame.id] = mine
        for other in survivors where !other.hasUsableText {
          guard let theirs = hashes[other.id] else { continue }
          if MeetingFrameSimilarity.similarity(mine, theirs) >= imageSimilarityCeiling {
            duplicate = true
            break
          }
        }
      }
      if duplicate {
        outcome.drops["near-duplicate of a frame already kept", default: 0] += 1
        continue
      }
      survivors.append(frame)
    }

    // Bound it, spread across the meeting so the last ten minutes are represented as well as the
    // first — a meeting's decisions are usually at the end.
    if survivors.count > candidateCeiling {
      let step = Double(survivors.count) / Double(candidateCeiling)
      let picked = (0..<candidateCeiling).map { survivors[min(Int(Double($0) * step), survivors.count - 1)] }
      outcome.drops["over the candidate ceiling", default: 0] += survivors.count - picked.count
      survivors = picked
    }

    outcome.candidates = survivors
    return outcome
  }
}
