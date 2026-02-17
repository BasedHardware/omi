import Foundation
import Vision
import AppKit
import Sentry

/// Represents a text block with its bounding box (in normalized coordinates 0-1)
struct OCRTextBlock: Codable, Equatable {
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
        let screenY = (1.0 - y - height) * imageSize.height // Flip Y
        let screenWidth = width * imageSize.width
        let screenHeight = height * imageSize.height
        return CGRect(x: screenX, y: screenY, width: screenWidth, height: screenHeight)
    }
}

/// Complete OCR result with all text blocks
struct OCRResult: Codable, Equatable {
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
            print("[OCR] contextSnippet bounds check failed: start=\(contextStart) end=\(contextEnd) textLen=\(fullText.count) query='\(query.prefix(20))'")
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

/// Apple Vision-based OCR service for extracting text from screenshots
actor RewindOCRService {
    static let shared = RewindOCRService()

    private init() {}

    // MARK: - Frame Deduplication

    private var lastFrameFingerprint: UInt64?

    /// Hamming distance threshold for dHash deduplication.
    /// Distances at or below this value are considered "same screen" (cursor blink, spinner, clock tick).
    /// Empirically: spinner animation = 1, cursor shift = 4, real content change = 23.
    private let dedupThreshold = 5

    /// Track last-logged OCR mode to only log on change
    private var lastLoggedOCRMode: String?

    /// Compute a perceptual difference hash (dHash) of a CGImage.
    /// Downscales to 9x8 grayscale, then compares each pixel to its right neighbor
    /// to produce a 64-bit hash. Small localized changes (cursor, spinners) affect
    /// only 1-2 bits, while real content changes affect many bits.
    static func dHash(of cgImage: CGImage) -> UInt64 {
        let w = 9, h = 8
        guard let ctx = CGContext(
            data: nil, width: w, height: h,
            bitsPerComponent: 8, bytesPerRow: w,
            space: CGColorSpaceCreateDeviceGray(),
            bitmapInfo: CGImageAlphaInfo.none.rawValue
        ) else { return 0 }

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
        let useFastOCR = UserDefaults.standard.object(forKey: "rewindOCRFast") as? Bool ?? true
        let modeName = useFastOCR ? "fast" : "accurate"
        let recognitionLevel: VNRequestTextRecognitionLevel = useFastOCR ? .fast : .accurate

        // Log OCR mode once, then only on change; set Sentry tag for queryability
        if modeName != lastLoggedOCRMode {
            log("RewindOCRService: OCR mode set to \(modeName)")
            SentrySDK.configureScope { scope in
                scope.setTag(value: modeName, key: "ocr_mode")
            }
            lastLoggedOCRMode = modeName
        }

        return try await withCheckedThrowingContinuation { continuation in
            let request = VNRecognizeTextRequest { request, error in
                if let error = error {
                    continuation.resume(throwing: RewindError.ocrFailed(error.localizedDescription))
                    return
                }

                guard let observations = request.results as? [VNRecognizedTextObservation] else {
                    continuation.resume(returning: OCRResult(fullText: "", blocks: [], processedAt: Date()))
                    return
                }

                var blocks: [OCRTextBlock] = []
                var fullTextLines: [String] = []

                for observation in observations {
                    guard let candidate = observation.topCandidates(1).first else { continue }

                    let boundingBox = observation.boundingBox
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
                continuation.resume(returning: result)
            }

            request.recognitionLevel = recognitionLevel
            request.usesLanguageCorrection = false
            request.recognitionLanguages = ["en-US"]

            let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])

            do {
                try handler.perform([request])
            } catch {
                continuation.resume(throwing: RewindError.ocrFailed(error.localizedDescription))
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
