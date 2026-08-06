//
//  SpineScreenIndex.swift — one day of screen capture, read cheaply.
//
//  The spine states two different things about the same day: *how many* frames there were (the day
//  header's "1,204 moments" and the hour rail's shape) and *which* frames a strip draws. Those have
//  opposite costs. The count and the histogram need every row in the day; the strip needs eight.
//
//  So this reads seven columns and nothing else. A `Screenshot` row carries OCR text, its
//  bounding-box JSON and an embedding blob, and `SELECT *` over a heavy day is tens of megabytes of
//  text nobody is going to read — which is exactly the shape of stall this surface cannot afford.
//  The projection here is small enough that the exact count and the exact histogram are affordable,
//  so the header never has to guess and the rail never has to be a sample.
//
//  Local hours, not UTC. GRDB stores `Date` as a UTC string, so bucketing in SQL would put the
//  user's evening in the wrong bar for most of the world. The bucketing happens in Swift, through
//  `Calendar`, which is also the only thing that gets a day with a DST transition in it right.
//

import Foundation
import GRDB

/// Reads one day of Rewind capture for the spine.
enum SpineScreenIndex {
  /// How many frames one day contributes to the strips.
  ///
  /// A day's rows are split into runs by `SpineComposer.clusters(of:)` and each run draws at most
  /// `SpineComposer.momentsPerStrip`, so this is a ceiling on the *sample*, not on what the header
  /// counts. 240 is generous enough that every cluster in a busy day has frames to show and small
  /// enough that a week of days stays a few thousand tiny structs.
  static let sampleCeiling = 240

  /// How long a read will wait for Rewind's database to finish opening.
  ///
  /// **This wait is the difference between a spine with screen moments in it and one without.**
  /// Rewind's pool opens asynchronously after launch, and the spine reads each day exactly once —
  /// so a read that lands in that window used to record "this day has no screen capture" and never
  /// look again. A freshly launched app showed an empty rail and empty strips for the rest of the
  /// session, which looked exactly like a user who has capture switched off.
  ///
  /// Twenty seconds is far longer than the pool takes and is bounded, so an account that genuinely
  /// has no Rewind database still resolves to an honest empty day rather than hanging.
  static let readinessTimeout: Duration = .seconds(20)
  private static let readinessPollInterval: Duration = .milliseconds(400)

  /// One day, or an empty day when Rewind genuinely has no database (capture never enabled).
  static func load(day: Date, calendar: Calendar = .current) async -> SpineDayScreen {
    let start = calendar.startOfDay(for: day)
    guard let end = calendar.date(byAdding: .day, value: 1, to: start) else { return .empty }
    guard let pool = await poolWhenReady() else { return .empty }

    // A frame in the chunk still being written cannot be decoded yet — the video has no moov atom
    // until it is finalised — so those rows are read but never drawn.
    let unfinalizedChunk = await VideoChunkEncoder.shared.currentChunkPath

    do {
      let rows = try await pool.read { db in
        try Row.fetchAll(
          db,
          sql: """
              SELECT id, timestamp, appName, windowTitle, imagePath, videoChunkPath, frameOffset
              FROM screenshots
              WHERE timestamp >= ? AND timestamp < ?
              ORDER BY timestamp DESC
            """,
          arguments: [start, end]
        )
      }
      return project(rows: rows, calendar: calendar, unfinalizedChunk: unfinalizedChunk)
    } catch {
      // A missing table or a database being migrated underneath us is a state the spine renders as
      // "no screen rows today", not as a failure worth interrupting the whole stream for.
      return .empty
    }
  }

  /// Rewind's pool, once it is open — or `nil` once the wait is spent.
  ///
  /// Polled rather than awaited on a signal because `RewindDatabase` publishes none; the poll is
  /// one actor hop every 400 ms against a `Bool`, which is cheaper than the alternative of reading
  /// the day wrongly and caching the wrong answer for the session.
  static func poolWhenReady(timeout: Duration = readinessTimeout) async -> DatabasePool? {
    if let pool = await RewindDatabase.shared.getDatabaseQueue() { return pool }
    let deadline = ContinuousClock.now.advanced(by: timeout)
    while ContinuousClock.now < deadline {
      try? await Task.sleep(for: readinessPollInterval)
      if Task.isCancelled { return nil }
      if let pool = await RewindDatabase.shared.getDatabaseQueue() { return pool }
    }
    return nil
  }

  /// Turns the raw projection into a day. Split out from the query so the counting, the local-hour
  /// bucketing and the even sampling are all testable without a database.
  static func project(
    rows: [Row],
    calendar: Calendar,
    unfinalizedChunk: String?
  ) -> SpineDayScreen {
    var hourCounts = [Int](repeating: 0, count: 24)
    var drawable: [SpineMoment] = []
    drawable.reserveCapacity(min(rows.count, sampleCeiling))

    for row in rows {
      guard let id: Int64 = row["id"], let timestamp: Date = row["timestamp"] else { continue }
      let hour = calendar.component(.hour, from: timestamp)
      if hour >= 0, hour < 24 { hourCounts[hour] += 1 }

      let videoChunkPath: String? = row["videoChunkPath"]
      guard videoChunkPath == nil || videoChunkPath != unfinalizedChunk else { continue }
      drawable.append(
        SpineMoment(
          id: id,
          timestamp: timestamp,
          appName: row["appName"] ?? "Unknown",
          windowTitle: row["windowTitle"],
          imagePath: row["imagePath"],
          videoChunkPath: videoChunkPath,
          frameOffset: row["frameOffset"]
        ))
    }

    return SpineDayScreen(
      total: rows.count,
      hourCounts: hourCounts,
      sampled: evenlySampled(drawable, ceiling: sampleCeiling)
    )
  }

  /// Keeps at most `ceiling` frames, spread evenly across the run rather than taken off the front.
  ///
  /// Taking the first N would show a busy day as its last twenty minutes and nothing else — the
  /// strips would all cluster at the top of the spine and the rest of the day would look empty.
  static func evenlySampled(_ moments: [SpineMoment], ceiling: Int) -> [SpineMoment] {
    guard ceiling > 0 else { return [] }
    guard moments.count > ceiling else { return moments }
    let step = Double(moments.count) / Double(ceiling)
    var sampled: [SpineMoment] = []
    sampled.reserveCapacity(ceiling)
    var cursor = 0.0
    while sampled.count < ceiling {
      let index = Int(cursor)
      guard index < moments.count else { break }
      sampled.append(moments[index])
      cursor += step
    }
    return sampled
  }
}
