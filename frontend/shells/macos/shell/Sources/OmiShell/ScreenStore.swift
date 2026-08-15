import AVFoundation
import CoreGraphics
import CoreMedia
import CoreVideo
import Foundation

struct ScreenIndexRow: Codable, Equatable {
  var id: String
  var capturedAt: String
  var appBundleId: String
  var appName: String
  var windowTitle: String
  var dhash: String
  var frameRef: String
  var chunkPath: String
  var frameOffset: Int
  var width: Int
  var height: Int
  var ocrCompleted: Bool
  var blockCount: Int
  var ingested: Bool
  var ocrJSON: String?
}

struct ScreenStoreMeta: Codable, Equatable {
  var clientDeviceId: String
  var exclusions: [String]
  var userRemovedDefaults: [String]
  var retentionDays: Int
  var hasRequestedPermission: Bool
  var lastSweepAt: String?
  var ingest: ScreenIngestCursorFile
  var pendingDeletes: [String]
  var framesStored: Int
}

struct ScreenIngestCursorFile: Codable, Equatable {
  var lastAcceptedId: String?
  var pendingIds: [String]
  var failureCount: Int
  var backoffUntil: String?
}

/// Local pixels + index. Lives under Application Support, never the repo tree.
final class ScreenLocalStore: @unchecked Sendable {
  let root: URL
  private let fm = FileManager.default
  private let lock = NSLock()
  private var rows: [ScreenIndexRow] = []
  private var rowsByRef: [String: ScreenIndexRow] = [:]
  private var meta: ScreenStoreMeta
  private var writer: ScreenChunkWriter?
  private var chunkOrdinal = 0
  private var firstChunk = true

  var framesStored: Int {
    lock.lock()
    defer { lock.unlock() }
    return rows.count
  }

  var bytesOnDisk: Int? {
    lock.lock()
    let dir = chunksDir
    lock.unlock()
    guard let enumerator = fm.enumerator(at: dir, includingPropertiesForKeys: [.fileSizeKey])
    else { return nil }
    var total = 0
    var sawAny = false
    for case let url as URL in enumerator {
      sawAny = true
      let values = try? url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
      if values?.isRegularFile == true, let size = values?.fileSize {
        total += size
      }
    }
    _ = sawAny
    let indexSize =
      (try? fm.attributesOfItem(atPath: indexURL.path)[.size] as? NSNumber)?.intValue ?? 0
    let metaSize =
      (try? fm.attributesOfItem(atPath: metaURL.path)[.size] as? NSNumber)?.intValue ?? 0
    return total + indexSize + metaSize
  }

  init(root: URL, omiBundleId: String) {
    self.root = root
    try? fm.createDirectory(at: root, withIntermediateDirectories: true)
    try? fm.createDirectory(
      at: root.appendingPathComponent("chunks", isDirectory: true),
      withIntermediateDirectories: true)
    if let loaded = Self.loadMeta(at: root.appendingPathComponent("meta.json")),
      let existingRows = Self.loadRows(at: root.appendingPathComponent("frames.jsonl"))
    {
      self.meta = loaded
      self.rows = existingRows
    } else {
      self.meta = ScreenStoreMeta(
        clientDeviceId: UUID().uuidString.lowercased(),
        exclusions: [],
        userRemovedDefaults: [],
        retentionDays: ScreenRetentionPolicy.defaultDays,
        hasRequestedPermission: false,
        lastSweepAt: nil,
        ingest: ScreenIngestCursorFile(
          lastAcceptedId: nil, pendingIds: [], failureCount: 0, backoffUntil: nil),
        pendingDeletes: [],
        framesStored: 0)
      self.rows = []
    }
    let merged = ScreenExclusionPolicy.mergeDefaults(
      stored: meta.exclusions,
      userRemoved: Set(meta.userRemovedDefaults),
      omiBundleId: omiBundleId)
    meta.exclusions = merged
    reindex()
    // Ordinal is process-local and used to be reset to 0 on every launch, so
    // the next writer reused chunks/chunk-000001.mp4, deleted it, and left
    // every historical row pointing at an empty file. Resume past the highest
    // ordinal already referenced or on disk.
    chunkOrdinal = Self.highestChunkOrdinal(root: root, rows: rows)
    persistMeta()
    retryPendingDeletes()
  }

  var clientDeviceId: String {
    lock.lock()
    defer { lock.unlock() }
    return meta.clientDeviceId
  }

  var exclusions: [String] {
    lock.lock()
    defer { lock.unlock() }
    return meta.exclusions
  }

  var hasRequestedPermission: Bool {
    lock.lock()
    defer { lock.unlock() }
    return meta.hasRequestedPermission
  }

  func markRequestedPermission() {
    lock.lock()
    meta.hasRequestedPermission = true
    persistMeta()
    lock.unlock()
  }

  func isExcluded(_ bundleId: String) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    return meta.exclusions.contains(bundleId)
  }

  func ingestCursor() -> ScreenIngestCursor {
    lock.lock()
    defer { lock.unlock() }
    return ScreenIngestCursor(
      lastAcceptedId: meta.ingest.lastAcceptedId,
      pendingIds: meta.ingest.pendingIds,
      failureCount: meta.ingest.failureCount,
      backoffUntil: meta.ingest.backoffUntil.flatMap(ScreenTime.parse))
  }

  func setIngestCursor(_ cursor: ScreenIngestCursor) {
    lock.lock()
    meta.ingest = ScreenIngestCursorFile(
      lastAcceptedId: cursor.lastAcceptedId,
      pendingIds: cursor.pendingIds,
      failureCount: cursor.failureCount,
      backoffUntil: cursor.backoffUntil.map(ScreenTime.wireTimestamp))
    persistMeta()
    lock.unlock()
  }

  func pendingOCRRows(limit: Int) -> [ScreenIndexRow] {
    lock.lock()
    defer { lock.unlock() }
    return rows.filter { row in
      ScreenIndexMeaning.isIndexed(ocrCompleted: row.ocrCompleted, blockCount: row.blockCount)
        && !row.ingested
    }.prefix(limit).map { $0 }
  }

  func markIngested(ids: [String]) {
    lock.lock()
    let set = Set(ids)
    for i in rows.indices where set.contains(rows[i].id) {
      rows[i].ingested = true
      rowsByRef[rows[i].frameRef] = rows[i]
    }
    persistRows()
    lock.unlock()
  }

  func setExclusions(_ bundleIds: [String], omiBundleId: String) -> (bundleIds: [String], retired: [String]) {
    lock.lock()
    let previous = meta.exclusions
    let unique = Array(Set(bundleIds).union([omiBundleId])).sorted()
    let removed = ScreenExclusionPolicy.removedDefaults(previous: previous, next: unique)
    meta.userRemovedDefaults = Array(Set(meta.userRemovedDefaults).union(removed)).sorted()
    meta.exclusions = unique
    let retired = retireLocked(matchingBundleIds: Set(unique))
    persistMeta()
    persistRows()
    lock.unlock()
    return (unique, retired)
  }

  var retentionDays: Int {
    lock.lock()
    defer { lock.unlock() }
    return meta.retentionDays
  }

  func setRetentionDays(_ days: Int, now: Date) -> [String] {
    lock.lock()
    meta.retentionDays = ScreenRetentionPolicy.normalize(days)
    let retired = sweepLocked(now: now)
    persistMeta()
    persistRows()
    lock.unlock()
    return retired
  }

  func sweepIfDue(now: Date) -> [String] {
    lock.lock()
    let last = meta.lastSweepAt.flatMap(ScreenTime.parse)
    guard ScreenRetentionPolicy.shouldSweep(lastSweepAt: last, now: now) else {
      lock.unlock()
      return []
    }
    let retired = sweepLocked(now: now)
    persistMeta()
    persistRows()
    lock.unlock()
    return retired
  }

  func rebuildIndex() -> (frames: Int, chunks: Int) {
    lock.lock()
    reindex()
    persistRows()
    persistMeta()
    let frames = rows.count
    let chunks = (try? fm.contentsOfDirectory(atPath: chunksDir.path).count) ?? 0
    lock.unlock()
    return (frames, chunks)
  }

  func row(frameRef: String) -> ScreenIndexRow? {
    lock.lock()
    defer { lock.unlock() }
    return rowsByRef[frameRef]
  }

  func applyRetiredRefs(_ refs: [String]) {
    lock.lock()
    _ = retireLocked(frameRefs: refs)
    persistRows()
    persistMeta()
    lock.unlock()
  }

  func appendFrame(
    image: CGImage,
    capturedAt: Date,
    appBundleId: String,
    appName: String,
    windowTitle: String,
    dhash: String,
    ocr: ScreenOCRAttachment?,
    allowWrite: Bool,
    frameRef: String? = nil
  ) throws -> ScreenIndexRow {
    lock.lock()
    defer { lock.unlock() }
    guard allowWrite else {
      throw ScreenStoreError.fenced
    }
    let clamped = ScreenImaging.clampLongEdge(image, maxLongEdge: ScreenImaging.captureLongEdge)
    if writer == nil || writer?.shouldRotate(now: capturedAt) == true {
      try rotateWriterLocked(now: capturedAt, width: clamped.width, height: clamped.height)
    }
    guard let writer else { throw ScreenStoreError.writerUnavailable }
    let offset = try writer.append(image: clamped, capturedAt: capturedAt)
    let ref = frameRef ?? UUID().uuidString.lowercased()
    let id = ref
    let ocrJSON: String?
    if let ocr {
      ocrJSON = ScreenIngestCodec.encodeOCR(ocr)
    } else {
      ocrJSON = nil
    }
    let row = ScreenIndexRow(
      id: id,
      capturedAt: ScreenTime.wireTimestamp(capturedAt),
      appBundleId: appBundleId,
      appName: appName,
      windowTitle: windowTitle,
      dhash: dhash,
      frameRef: ref,
      chunkPath: writer.relativePath,
      frameOffset: offset,
      width: clamped.width,
      height: clamped.height,
      ocrCompleted: ocr != nil,
      blockCount: ocr?.blocks.count ?? 0,
      ingested: false,
      ocrJSON: ocrJSON)
    rows.append(row)
    rowsByRef[ref] = row
    meta.framesStored = rows.count
    if ScreenIndexMeaning.isIndexed(ocrCompleted: row.ocrCompleted, blockCount: row.blockCount) {
      meta.ingest.pendingIds.append(row.id)
    }
    persistRows()
    persistMeta()
    return row
  }

  func decodeFrame(frameRef: String, maxLongEdge: Int?) throws -> (CGImage, Int, Int) {
    lock.lock()
    guard let row = rowsByRef[frameRef] else {
      lock.unlock()
      throw ScreenStoreError.unknownFrame
    }
    let url = root.appendingPathComponent(row.chunkPath)
    let offset = row.frameOffset
    lock.unlock()
    let image = try ScreenChunkWriter.decode(url: url, offsetMs: offset)
    let scaled: CGImage
    if let maxLongEdge {
      scaled = ScreenImaging.clampLongEdge(image, maxLongEdge: maxLongEdge)
    } else {
      scaled = image
    }
    return (scaled, scaled.width, scaled.height)
  }

  func finishWriter() {
    lock.lock()
    writer?.finish()
    writer = nil
    lock.unlock()
  }

  /// Drop one index row. The chunk file is deleted only when no remaining row
  /// still points at it.
  func dropFrame(frameRef: String) {
    lock.lock()
    defer { lock.unlock() }
    _ = retireLocked(frameRefs: [frameRef])
    persistRows()
    persistMeta()
  }

  private var chunksDir: URL { root.appendingPathComponent("chunks", isDirectory: true) }
  private var indexURL: URL { root.appendingPathComponent("frames.jsonl") }
  private var metaURL: URL { root.appendingPathComponent("meta.json") }

  private func rotateWriterLocked(now: Date, width: Int, height: Int) throws {
    writer?.finish()
    let duration: TimeInterval = firstChunk ? 5 : 60
    firstChunk = false
    chunkOrdinal += 1
    let name = String(format: "chunk-%06d.mp4", chunkOrdinal)
    let url = chunksDir.appendingPathComponent(name)
    writer = try ScreenChunkWriter(
      url: url,
      relativePath: "chunks/\(name)",
      start: now,
      duration: duration,
      width: width,
      height: height)
  }

  private func sweepLocked(now: Date) -> [String] {
    meta.lastSweepAt = ScreenTime.wireTimestamp(now)
    let days = meta.retentionDays
    var retired: [String] = []
    var kept: [ScreenIndexRow] = []
    for row in rows {
      guard let captured = ScreenTime.parse(row.capturedAt) else {
        kept.append(row)
        continue
      }
      if ScreenRetentionPolicy.isExpired(capturedAt: captured, now: now, days: days) {
        retired.append(row.frameRef)
        enqueueDeleteLocked(row.chunkPath)
      } else {
        kept.append(row)
      }
    }
    rows = kept
    reindex()
    retryPendingDeletes()
    return retired
  }

  private func retireLocked(matchingBundleIds bundleIds: Set<String>) -> [String] {
    var retired: [String] = []
    var kept: [ScreenIndexRow] = []
    for row in rows {
      if bundleIds.contains(row.appBundleId) {
        retired.append(row.frameRef)
        enqueueDeleteLocked(row.chunkPath)
      } else {
        kept.append(row)
      }
    }
    rows = kept
    reindex()
    retryPendingDeletes()
    return retired
  }

  private func retireLocked(frameRefs: [String]) -> [String] {
    let set = Set(frameRefs)
    var retired: [String] = []
    var kept: [ScreenIndexRow] = []
    for row in rows {
      if set.contains(row.frameRef) || set.contains(row.id) {
        retired.append(row.frameRef)
        enqueueDeleteLocked(row.chunkPath)
      } else {
        kept.append(row)
      }
    }
    rows = kept
    reindex()
    retryPendingDeletes()
    return retired
  }

  private func enqueueDeleteLocked(_ relative: String) {
    if !meta.pendingDeletes.contains(relative) {
      meta.pendingDeletes.append(relative)
    }
  }

  private func retryPendingDeletes() {
    var remaining: [String] = []
    let stillUsed = Set(rows.map(\.chunkPath))
    for relative in meta.pendingDeletes {
      if stillUsed.contains(relative) {
        remaining.append(relative)
        continue
      }
      let url = root.appendingPathComponent(relative)
      do {
        if fm.fileExists(atPath: url.path) {
          try fm.removeItem(at: url)
        }
      } catch {
        remaining.append(relative)
      }
    }
    meta.pendingDeletes = remaining
  }

  private static func highestChunkOrdinal(root: URL, rows: [ScreenIndexRow]) -> Int {
    var highest = 0
    let parse: (String) -> Int? = { name in
      let base = URL(fileURLWithPath: name).lastPathComponent
      guard base.hasPrefix("chunk-"), base.hasSuffix(".mp4") else { return nil }
      let digits = base.dropFirst("chunk-".count).dropLast(".mp4".count)
      return Int(digits)
    }
    for row in rows {
      if let n = parse(row.chunkPath) { highest = max(highest, n) }
    }
    let chunks = root.appendingPathComponent("chunks", isDirectory: true)
    if let files = try? FileManager.default.contentsOfDirectory(
      at: chunks, includingPropertiesForKeys: nil)
    {
      for url in files {
        if let n = parse(url.lastPathComponent) { highest = max(highest, n) }
      }
    }
    return highest
  }

  private func reindex() {
    rowsByRef = [:]
    for row in rows { rowsByRef[row.frameRef] = row }
    meta.framesStored = rows.count
  }

  private func persistRows() {
    let lines = rows.compactMap { row -> String? in
      guard let data = try? JSONEncoder().encode(row),
        let text = String(data: data, encoding: .utf8)
      else { return nil }
      return text
    }
    try? lines.joined(separator: "\n").write(to: indexURL, atomically: true, encoding: .utf8)
  }

  private func persistMeta() {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    guard let data = try? encoder.encode(meta) else { return }
    try? data.write(to: metaURL, options: .atomic)
  }

  private static func loadMeta(at url: URL) -> ScreenStoreMeta? {
    guard let data = try? Data(contentsOf: url) else { return nil }
    return try? JSONDecoder().decode(ScreenStoreMeta.self, from: data)
  }

  private static func loadRows(at url: URL) -> [ScreenIndexRow]? {
    guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [] }
    let decoder = JSONDecoder()
    return text.split(separator: "\n").compactMap { line in
      guard let data = line.data(using: .utf8) else { return nil }
      return try? decoder.decode(ScreenIndexRow.self, from: data)
    }
  }
}

enum ScreenStoreError: Error {
  case fenced
  case writerUnavailable
  case unknownFrame
  case decodeFailed
}

final class ScreenChunkWriter {
  let url: URL
  let relativePath: String
  let start: Date
  let duration: TimeInterval
  private let writer: AVAssetWriter
  private let input: AVAssetWriterInput
  private let adaptor: AVAssetWriterInputPixelBufferAdaptor
  private var started = false
  private var finished = false

  init(url: URL, relativePath: String, start: Date, duration: TimeInterval, width: Int, height: Int)
    throws
  {
    self.url = url
    self.relativePath = relativePath
    self.start = start
    self.duration = duration
    try? FileManager.default.removeItem(at: url)
    let writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
    let evenW = max(2, width - width % 2)
    let evenH = max(2, height - height % 2)
    let settings: [String: Any] = [
      AVVideoCodecKey: AVVideoCodecType.hevc,
      AVVideoWidthKey: evenW,
      AVVideoHeightKey: evenH,
    ]
    let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
    input.expectsMediaDataInRealTime = false
    let adaptor = AVAssetWriterInputPixelBufferAdaptor(
      assetWriterInput: input,
      sourcePixelBufferAttributes: [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
        kCVPixelBufferWidthKey as String: evenW,
        kCVPixelBufferHeightKey as String: evenH,
      ])
    guard writer.canAdd(input) else { throw ScreenStoreError.writerUnavailable }
    writer.add(input)
    self.writer = writer
    self.input = input
    self.adaptor = adaptor
  }

  func shouldRotate(now: Date) -> Bool {
    now.timeIntervalSince(start) >= duration
  }

  func append(image: CGImage, capturedAt: Date) throws -> Int {
    if finished { throw ScreenStoreError.writerUnavailable }
    if !started {
      guard writer.startWriting() else { throw ScreenStoreError.writerUnavailable }
      writer.startSession(atSourceTime: .zero)
      started = true
    }
    let offsetMs = max(0, Int((capturedAt.timeIntervalSince(start) * 1000).rounded(.towardZero)))
    let time = CMTime(value: CMTimeValue(offsetMs), timescale: 1000)
    guard let buffer = Self.pixelBuffer(from: image) else { throw ScreenStoreError.writerUnavailable }
    var spins = 0
    while !input.isReadyForMoreMediaData && spins < 200 {
      Thread.sleep(forTimeInterval: 0.01)
      spins += 1
    }
    guard adaptor.append(buffer, withPresentationTime: time) else {
      throw ScreenStoreError.writerUnavailable
    }
    return offsetMs
  }

  func finish() {
    guard started, !finished else { return }
    finished = true
    input.markAsFinished()
    let lock = DispatchSemaphore(value: 0)
    writer.finishWriting { lock.signal() }
    _ = lock.wait(timeout: .now() + 5)
  }

  static func decode(url: URL, offsetMs: Int) throws -> CGImage {
    let asset = AVURLAsset(url: url)
    let generator = AVAssetImageGenerator(asset: asset)
    generator.appliesPreferredTrackTransform = true
    generator.requestedTimeToleranceBefore = .zero
    generator.requestedTimeToleranceAfter = .zero
    let time = CMTime(value: CMTimeValue(offsetMs), timescale: 1000)
    var actual = CMTime.zero
    let image = try generator.copyCGImage(at: time, actualTime: &actual)
    return image
  }

  private static func pixelBuffer(from image: CGImage) -> CVPixelBuffer? {
    let width = image.width
    let height = image.height
    var buffer: CVPixelBuffer?
    let status = CVPixelBufferCreate(
      kCFAllocatorDefault,
      width,
      height,
      kCVPixelFormatType_32BGRA,
      [
        kCVPixelBufferCGImageCompatibilityKey: true,
        kCVPixelBufferCGBitmapContextCompatibilityKey: true,
      ] as CFDictionary,
      &buffer)
    guard status == kCVReturnSuccess, let buffer else { return nil }
    CVPixelBufferLockBaseAddress(buffer, [])
    defer { CVPixelBufferUnlockBaseAddress(buffer, []) }
    guard let dest = CVPixelBufferGetBaseAddress(buffer) else { return nil }
    let ctx = CGContext(
      data: dest,
      width: width,
      height: height,
      bitsPerComponent: 8,
      bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
      space: CGColorSpaceCreateDeviceRGB(),
      bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue
        | CGBitmapInfo.byteOrder32Little.rawValue)
    ctx?.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
    return buffer
  }
}
