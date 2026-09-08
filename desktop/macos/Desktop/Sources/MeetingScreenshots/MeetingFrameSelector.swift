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

  struct Outcome: Sendable {
    var candidates: [MeetingFrameCandidate] = []
    var framesInWindow = 0
    /// Why frames were dropped, for the diagnostics surface. A gate nobody can see the workings of
    /// is a gate nobody can debug when it silently returns nothing.
    var drops: [String: Int] = [:]
  }

  /// Every frame captured inside a conversation's window, narrowed to a bounded candidate set.
  static func selectCandidates(from start: Date, to end: Date) async -> Outcome {
    guard end > start else { return Outcome() }
    guard let pool = await SpineScreenIndex.poolWhenReady() else { return Outcome() }

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
      return Outcome()
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
        outcome.drops["chunk still being written", default: 0] += 1
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
