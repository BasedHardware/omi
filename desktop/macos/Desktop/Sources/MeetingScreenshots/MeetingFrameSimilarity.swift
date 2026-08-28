//
//  MeetingFrameSimilarity.swift — "is this the same screen I already kept?"
//
//  Two implementations of one question, because the corpus forces it. Where OCR ran, comparing the
//  text is cheap and exact enough. Where it did not — which is most of the time, see
//  `MeetingFrameSelector` — the only thing left to compare is the pixels.
//
//  The image path is a difference hash (dHash): decode small, greyscale, compare each pixel to its
//  right-hand neighbour, pack the 64 comparisons into a word. It is deliberately not a checksum —
//  two frames of the same document one scroll-line apart must read as the same screen, and a hash
//  that changes when one pixel changes would call them different.
//

import CoreGraphics
import Foundation

#if canImport(AppKit)
  import AppKit
#endif

enum MeetingFrameSimilarity {

  // MARK: - Text

  /// Word 5-grams. Shingles rather than a bag of words because a bag of words calls two different
  /// pages of the same app similar merely for sharing its chrome.
  static func shingles(_ text: String, size: Int = 5) -> Set<Int> {
    let words = text.lowercased().split { !$0.isLetter && !$0.isNumber }.map(String.init)
    guard words.count >= size else {
      return words.isEmpty ? [] : [words.joined(separator: " ").hashValue]
    }
    var out = Set<Int>()
    out.reserveCapacity(words.count - size + 1)
    for i in 0...(words.count - size) {
      out.insert(words[i..<(i + size)].joined(separator: " ").hashValue)
    }
    return out
  }

  static func jaccard(_ a: Set<Int>, _ b: Set<Int>) -> Double {
    if a.isEmpty || b.isEmpty { return 0 }
    let intersection = a.intersection(b).count
    if intersection == 0 { return 0 }
    return Double(intersection) / Double(a.union(b).count)
  }

  // MARK: - Pixels

  /// The dHash grid. 9 wide so that eight left-to-right comparisons fit per row.
  private static let hashWidth = 9
  private static let hashHeight = 8

  /// A 64-bit difference hash of a frame, or nil when its pixels are unrecoverable — a chunk that
  /// retention removed, or one abandoned zero-byte mid-write. **Unrecoverable is a normal state**,
  /// not a failure: the frame simply cannot participate in image similarity and is kept.
  static func perceptualHash(of candidate: MeetingFrameCandidate) async -> UInt64? {
    #if canImport(AppKit)
      return await hashOnMainActor(candidate.moment.screenshot)
    #else
      return nil
    #endif
  }

  #if canImport(AppKit)
    /// Hash the thumbnail where the thumbnail lives.
    ///
    /// `RewindThumbnailLoader` is `@MainActor` and `NSImage` is not `Sendable`, so handing the
    /// picture back to a nonisolated caller is a strict-concurrency error — the pinned Xcode 16.4
    /// toolchain rejects it even though newer Swift accepts it. Doing the whole hash on the main
    /// actor and returning only the 64 bits means nothing non-`Sendable` crosses at all. The grid
    /// is 9x8, so the draw is negligible work to keep there.
    @MainActor
    private static func hashOnMainActor(_ screenshot: Screenshot) async -> UInt64? {
      guard
        let image = await RewindThumbnailLoader.shared.thumbnail(for: screenshot),
        let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil)
      else { return nil }
      return dHash(cgImage)
    }
  #endif

  /// Fraction of the 64 bits two hashes agree on. 1.0 is identical.
  static func similarity(_ a: UInt64, _ b: UInt64) -> Double {
    Double(64 - (a ^ b).nonzeroBitCount) / 64.0
  }

  private static func dHash(_ image: CGImage) -> UInt64? {
    let width = hashWidth
    let height = hashHeight
    var pixels = [UInt8](repeating: 0, count: width * height)
    guard
      let context = CGContext(
        data: &pixels,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: width,
        space: CGColorSpaceCreateDeviceGray(),
        bitmapInfo: CGImageAlphaInfo.none.rawValue)
    else { return nil }

    context.interpolationQuality = .low
    context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))

    var hash: UInt64 = 0
    var bit = 0
    for y in 0..<height {
      for x in 0..<(width - 1) {
        if pixels[y * width + x] > pixels[y * width + x + 1] {
          hash |= (1 << UInt64(bit))
        }
        bit += 1
      }
    }
    return hash
  }
}
