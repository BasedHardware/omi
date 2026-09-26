import AppKit
import Foundation
import Sentry
import Vision

/// Represents a text block with its bounding box (in normalized coordinates 0-1)
struct OCRTextBlock: Codable, Equatable, Sendable {
  let text: String
  /// Bounding box in normalized coordinates (0-1), origin at bottom-left (Vision coordinate system)
  let x: Double
  let y: Double
  let width: Double
  let height: Double
  let confidence: Double

  /// Convert to screen coordinates for a given image size
  func screenRect(for imageSize: CGSize) -> CGRect {
    // Vision uses bottom-left origin, convert to top-left origin for display
    let screenX = x * imageSize.width
    let screenY = (1.0 - y - height) * imageSize.height  // Flip Y
    let screenWidth = width * imageSize.width
    let screenHeight = height * imageSize.height
    return CGRect(x: screenX, y: screenY, width: screenWidth, height: screenHeight)
  }
}

/// Complete OCR result with all text blocks
struct OCRResult: Codable, Equatable, Sendable {
  let fullText: String
  let blocks: [OCRTextBlock]
  let processedAt: Date

  /// Get all blocks that contain the search query (case-insensitive)
  func blocksContaining(_ query: String) -> [OCRTextBlock] {
    let lowercasedQuery = query.lowercased()
    return blocks.filter { $0.text.lowercased().contains(lowercasedQuery) }
  }

  /// Get context snippet around a search match
  func contextSnippet(for query: String, maxLength: Int = 150) -> String? {
    let lowercasedQuery = query.lowercased()
    let lowercasedText = fullText.lowercased()

    guard let range = lowercasedText.range(of: lowercasedQuery) else {
      return nil
    }

    // Use the lowercased string for distance calculation to avoid String.Index incompatibility crash
    let matchStart = lowercasedText.distance(from: lowercasedText.startIndex, to: range.lowerBound)
    let contextStart = max(0, matchStart - 50)
    let contextEnd = min(fullText.count, matchStart + query.count + 100)

    // Safely create indices with bounds checking
    guard contextStart <= fullText.count, contextEnd <= fullText.count, contextStart <= contextEnd else {
      // Log for debugging - this indicates a Unicode edge case
      print(
        "[OCR] contextSnippet bounds check failed: start=\(contextStart) end=\(contextEnd) textLen=\(fullText.count) query='\(query.prefix(20))'"
      )
      return nil
    }

    let startIndex = fullText.index(fullText.startIndex, offsetBy: contextStart)
    let endIndex = fullText.index(fullText.startIndex, offsetBy: contextEnd)

    var snippet = String(fullText[startIndex..<endIndex])

    // Clean up and add ellipsis
    snippet = snippet.replacingOccurrences(of: "\n", with: " ")
    if contextStart > 0 { snippet = "..." + snippet }
    if contextEnd < fullText.count { snippet = snippet + "..." }

    return snippet
  }
}

/// Owns exactly one terminal result across Vision's two completion paths.
///
/// `VNImageRequestHandler.perform` may synchronously throw after the request
/// callback has already fired (or a late callback may arrive after a throw).
/// Both paths therefore compete through this lock before touching Swift's
/// checked continuation. The losing path is an expected no-op, not a second
/// resume that traps the process.
final class VisionRequestCompletion<Value: Sendable>: @unchecked Sendable {
  private let lock = NSLock()
  private var continuation: CheckedContinuation<Value, Error>?

  init(_ continuation: CheckedContinuation<Value, Error>) {
    self.continuation = continuation
  }

  @discardableResult
  func complete(_ result: Result<Value, Error>) -> Bool {
    let continuation = lock.withLock {
      let claimed = self.continuation
      self.continuation = nil
      return claimed
    }
    guard let continuation else { return false }
    continuation.resume(with: result)
    return true
  }
}

/// Apple Vision-based OCR service for extracting text from screenshots
actor RewindOCRService {
  static let shared = RewindOCRService()

  /// Recognition languages passed to `VNRecognizeTextRequest`.
  ///
  /// Resolved once from the user's own preferred languages instead of a pinned
  /// locale: a language absent from this list is not recognised poorly, it is
  /// not recognised at all, so pinning `en-US` left every non-Latin script
  /// silently unsearchable.
  ///
  /// Still held as a process-lifetime constant so the bridged NSArray backing
  /// storage can never be released while Vision's TextRecognition framework
  /// enumerates it asynchronously on `com.apple.root.utility-qos.cooperative`.
  /// A Swift array literal assigned to `recognitionLanguages` has its storage
  /// tied to the call frame; once the request is dispatched to a background
  /// queue the storage can be freed, leaving TextRecognition iterating an
  /// `__EmptyArrayStorage` and tripping `_assertionFailure` (EXC_BREAKPOINT /
  /// SIGTRAP). Resolving into a `static let` keeps exactly one pinned array for
  /// the process lifetime, so that race stays closed. See #5891, #5151.
  private static let recognitionLanguages: [String] = resolveRecognitionLanguages(
    preferred: Locale.preferredLanguages,
    supported: visionSupportedRecognitionLanguages()
  )

  /// Languages Vision can actually recognise at the level this service uses.
  ///
  /// Falls back to English when the query fails rather than propagating: an
  /// unavailable capability list must not take OCR down with it.
  static func visionSupportedRecognitionLanguages() -> [String] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = recognitionLevel()
    request.revision = VNRecognizeTextRequest.currentRevision
    return (try? request.supportedRecognitionLanguages()) ?? ["en-US"]
  }

  /// Picks the recognition languages for a user, in Vision's priority order.
  ///
  /// Pure and injectable so the ordering, filtering and fallback rules are
  /// testable without invoking Vision or changing the host's locale.
  ///
  /// Preferred languages Vision does not support are dropped rather than passed
  /// through: `perform` throws on an unsupported tag, which would fail the whole
  /// request and turn a partial-recognition bug into total OCR loss.
  static func resolveRecognitionLanguages(
    preferred: [String],
    supported: [String]
  ) -> [String] {
    guard !supported.isEmpty else { return ["en-US"] }

    var resolved: [String] = []
    var seen = Set<String>()

    func append(_ tag: String) {
      guard seen.insert(tag).inserted else { return }
      resolved.append(tag)
    }

    // Vision treats the list as a priority order, so the user's own languages
    // lead.
    for tag in preferred {
      if let match = bestSupportedMatch(for: tag, in: supported) {
        append(match)
      }
    }

    // English is retained even when it is not a preferred language. Screen text
    // is routinely mixed — identifiers, URLs, product names — and dropping it
    // would regress the Latin half of the very lines this is meant to fix.
    for fallback in ["en-US", "en"] {
      if let match = bestSupportedMatch(for: fallback, in: supported) {
        append(match)
        break
      }
    }

    // Never hand back a tag Vision did not report: an unsupported language makes
    // `perform` throw and takes the whole request down. When the capability list
    // shares nothing with this user, fall back to the first language Vision does
    // support. ["en-US"] is reserved for the empty-capability case above, where
    // there is no reported list to choose from.
    return resolved.isEmpty ? [supported[0]] : resolved
  }

  /// Matches a BCP-47 tag against Vision's supported tags: the exact tag first,
  /// then the same language *and script*.
  ///
  /// Script matters, and collapsing to the primary language gets it wrong: `zh`
  /// alone would let a `zh-TW` reader be handed Vision's `zh-Hans` scope and
  /// recognised with the Simplified model. Comparing maximised identifiers keeps
  /// `zh-TW` on `zh-Hant`, while still letting `ja` reach `ja-JP` and `en-GB`
  /// reach `en-US`, because those agree once likely subtags are filled in.
  private static func bestSupportedMatch(for tag: String, in supported: [String]) -> String? {
    if let exact = supported.first(where: { $0.caseInsensitiveCompare(tag) == .orderedSame }) {
      return exact
    }
    let requested = Self.languageAndScript(of: tag)
    return supported.first { Self.languageAndScript(of: $0) == requested }
  }

  /// Language and script for a tag, with likely subtags filled in, so tags that
  /// name the same written language compare equal regardless of how they spell
  /// it (`zh-TW` and `zh-Hant`; `ja` and `ja-JP`).
  static func languageAndScript(of tag: String) -> String {
    let maximal = Locale.Language(identifier: tag).maximalIdentifier
    let expanded = Locale.Language(identifier: maximal)
    let language = expanded.languageCode?.identifier.lowercased() ?? tag.lowercased()
    let script = expanded.script?.identifier.lowercased() ?? ""
    return "\(language)-\(script)"
  }

  private init() {}

  // MARK: - Frame Deduplication

  private var lastFrameFingerprint: UInt64?

  /// Hamming distance threshold for dHash deduplication.
  /// Distances at or below this value are considered "same screen" (cursor blink, spinner, clock tick).
  /// Empirically: spinner animation = 1, cursor shift = 4, real content change = 23.
  private let dedupThreshold = 5

  /// Track last-logged OCR mode to only log on change
  private var lastLoggedOCRMode: String?

  static func recognitionLevel() -> VNRequestTextRecognitionLevel {
    .accurate
  }

  static func usesLanguageCorrection() -> Bool {
    true
  }

  /// Bridges a callback-style Vision request whose synchronous `perform` call
  /// can also throw. Keeping this boundary generic makes the competing terminal
  /// paths deterministically testable without mocking Vision framework types.
  nonisolated static func awaitSingleVisionCompletion<Value: Sendable>(
    perform: (@escaping @Sendable (Result<Value, Error>) -> Bool) throws -> Void
  ) async throws -> Value {
    try await withCheckedThrowingContinuation { continuation in
      let completion = VisionRequestCompletion(continuation)
      let finish: @Sendable (Result<Value, Error>) -> Bool = { result in
        completion.complete(result)
      }
      do {
        try perform(finish)
      } catch {
        _ = completion.complete(.failure(error))
      }
    }
  }

  /// Compute a perceptual difference hash (dHash) of a CGImage.
  /// Downscales to 9x8 grayscale, then compares each pixel to its right neighbor
  /// to produce a 64-bit hash. Small localized changes (cursor, spinners) affect
  /// only 1-2 bits, while real content changes affect many bits.
  static func dHash(of cgImage: CGImage) -> UInt64 {
    let w = 9
    let h = 8
    guard
      let ctx = CGContext(
        data: nil, width: w, height: h,
        bitsPerComponent: 8, bytesPerRow: w,
        space: CGColorSpaceCreateDeviceGray(),
        bitmapInfo: CGImageAlphaInfo.none.rawValue
      )
    else { return 0 }

    ctx.interpolationQuality = .low
    ctx.draw(cgImage, in: CGRect(x: 0, y: 0, width: w, height: h))

    guard let data = ctx.data else { return 0 }
    let pixels = data.assumingMemoryBound(to: UInt8.self)

    var hash: UInt64 = 0
    for row in 0..<h {
      for col in 0..<(w - 1) {
        let idx = row * w + col
        if pixels[idx] > pixels[idx + 1] {
          hash |= 1 << (row * (w - 1) + col)
        }
      }
    }
    return hash
  }

  /// dHash computed through an intermediate downscale to the preview-capture envelope.
  ///
  /// The proactive capture pipeline compares hashes of ≤80px preview grabs against a
  /// history that also receives the hash of every full capture. Hashing a
  /// full-resolution frame straight into dHash's 9x8 grid aliases differently than
  /// hashing an 80px preview of the same screen, so cross-scale comparisons read as
  /// "changed", defeat the preview-similarity skip, and trigger unnecessary full
  /// captures (and the Gemini calls behind them). Downscaling to the same ≤80px
  /// envelope first keeps both sides of the comparison in one representation.
  static func previewScaleDHash(of cgImage: CGImage, maxSize: Int = 80) -> UInt64 {
    let width = cgImage.width
    let height = cgImage.height
    guard width > maxSize || height > maxSize else { return dHash(of: cgImage) }
    let scale = Double(maxSize) / Double(max(width, height))
    let w = max(1, Int((Double(width) * scale).rounded()))
    let h = max(1, Int((Double(height) * scale).rounded()))
    guard
      let ctx = CGContext(
        data: nil, width: w, height: h,
        bitsPerComponent: 8, bytesPerRow: w,
        space: CGColorSpaceCreateDeviceGray(),
        bitmapInfo: CGImageAlphaInfo.none.rawValue
      )
    else { return dHash(of: cgImage) }
    ctx.interpolationQuality = .medium
    ctx.draw(cgImage, in: CGRect(x: 0, y: 0, width: w, height: h))
    guard let downscaled = ctx.makeImage() else { return dHash(of: cgImage) }
    return dHash(of: downscaled)
  }

  /// Check if a frame should skip OCR because it's perceptually identical to the previous frame.
  /// Uses dHash with Hamming distance — small changes (cursor blink, spinners) produce
  /// distance 1-4 and are skipped, while real content changes produce distance 10+ and trigger OCR.
  func shouldSkipOCR(for cgImage: CGImage) async -> Bool {
    let fingerprint = Self.dHash(of: cgImage)
    defer { lastFrameFingerprint = fingerprint }
    guard let last = lastFrameFingerprint else { return false }
    let distance = (fingerprint ^ last).nonzeroBitCount
    return distance <= dedupThreshold
  }

  // MARK: - Text Extraction with Bounding Boxes

  /// Extract text with bounding boxes from JPEG image data using Apple Vision
  func extractTextWithBounds(from imageData: Data) async throws -> OCRResult {
    guard let nsImage = NSImage(data: imageData) else {
      throw RewindError.invalidImage
    }

    var rect = NSRect(origin: .zero, size: nsImage.size)
    guard let cgImage = nsImage.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
      throw RewindError.invalidImage
    }

    return try await extractTextWithBounds(from: cgImage)
  }

  /// Extract text with bounding boxes from a CGImage
  func extractTextWithBounds(from cgImage: CGImage) async throws -> OCRResult {
    let modeName = "accurate"

    // Log OCR mode once, then only on change; set Sentry tag for queryability
    if modeName != lastLoggedOCRMode {
      log("RewindOCRService: OCR mode set to \(modeName)")
      SentrySDK.configureScope { scope in
        scope.setTag(value: modeName, key: "ocr_mode")
      }
      lastLoggedOCRMode = modeName
    }

    return try await Self.awaitSingleVisionCompletion { finish in
      let request = VNRecognizeTextRequest { request, error in
        if let error = error {
          _ = finish(.failure(RewindError.ocrFailed(error.localizedDescription)))
          return
        }

        guard let observations = request.results as? [VNRecognizedTextObservation] else {
          _ = finish(.success(OCRResult(fullText: "", blocks: [], processedAt: Date())))
          return
        }

        // Defensive copy — Vision framework results are bridged NSArray objects
        // that can trigger EXC_BREAKPOINT / _objectAt assertion failures if the
        // underlying buffer is mutated or released during enumeration (see #5891, #5151).
        let safeObservations = Array(observations)

        var blocks: [OCRTextBlock] = []
        var fullTextLines: [String] = []

        for observation in safeObservations {
          let candidates = observation.topCandidates(1)
          guard !candidates.isEmpty, let candidate = candidates.first else { continue }

          let boundingBox = observation.boundingBox
          // Validate bounding box values are finite before using them
          guard boundingBox.origin.x.isFinite, boundingBox.origin.y.isFinite,
            boundingBox.width.isFinite, boundingBox.height.isFinite
          else { continue }

          let block = OCRTextBlock(
            text: candidate.string,
            x: Double((boundingBox.origin.x * 1000).rounded()) / 1000,
            y: Double((boundingBox.origin.y * 1000).rounded()) / 1000,
            width: Double((boundingBox.width * 1000).rounded()) / 1000,
            height: Double((boundingBox.height * 1000).rounded()) / 1000,
            confidence: (Double(candidate.confidence) * 1000).rounded() / 1000
          )
          blocks.append(block)
          fullTextLines.append(candidate.string)
        }

        let result = OCRResult(
          fullText: fullTextLines.joined(separator: "\n"),
          blocks: blocks,
          processedAt: Date()
        )
        _ = finish(.success(result))
      }

      request.recognitionLevel = Self.recognitionLevel()
      request.usesLanguageCorrection = Self.usesLanguageCorrection()
      request.recognitionLanguages = Self.recognitionLanguages

      let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])

      do {
        try handler.perform([request])
      } catch {
        throw RewindError.ocrFailed(error.localizedDescription)
      }
    }
  }

  // MARK: - Legacy Text-Only Extraction (for compatibility)

  /// Extract text from JPEG image data using Apple Vision
  func extractText(from imageData: Data) async throws -> String {
    let result = try await extractTextWithBounds(from: imageData)
    return result.fullText
  }

  /// Extract text from a CGImage
  func extractText(from cgImage: CGImage) async throws -> String {
    let result = try await extractTextWithBounds(from: cgImage)
    return result.fullText
  }

  /// Extract text from an image file at a URL
  func extractText(from url: URL) async throws -> String {
    let data = try Data(contentsOf: url)
    return try await extractText(from: data)
  }

  // MARK: - Batch Processing

  /// Process multiple images and return results with bounding boxes
  func extractTextBatchWithBounds(from imageDatas: [Data]) async -> [(index: Int, result: Result<OCRResult, Error>)] {
    var results: [(index: Int, result: Result<OCRResult, Error>)] = []

    for (index, data) in imageDatas.enumerated() {
      do {
        let ocrResult = try await extractTextWithBounds(from: data)
        results.append((index, .success(ocrResult)))
      } catch {
        results.append((index, .failure(error)))
      }
    }

    return results
  }
}
