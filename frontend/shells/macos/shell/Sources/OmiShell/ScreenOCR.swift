import CoreGraphics
import Foundation
import Vision

struct ScreenOCRBlock: Equatable {
  var id: String
  var text: String
  var x: Double
  var y: Double
  var w: Double
  var h: Double
  var confidence: Double
}

struct ScreenOCRAttachment: Equatable {
  var fullText: String
  var blocks: [ScreenOCRBlock]
}

enum ScreenOCR {
  /// One Vision pipeline: accurate, language correction, en-US.
  /// Bounding boxes are normalized top-left origin as the wire schema requires.
  static func recognize(_ image: CGImage) -> ScreenOCRAttachment? {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["en-US"]
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    do {
      try handler.perform([request])
    } catch {
      return nil
    }
    guard let observations = request.results, !observations.isEmpty else { return nil }
    var blocks: [ScreenOCRBlock] = []
    var texts: [String] = []
    for (index, observation) in observations.enumerated() {
      guard let candidate = observation.topCandidates(1).first else { continue }
      let box = observation.boundingBox
      // Vision is bottom-left origin; wire is top-left.
      let x = clamp01(box.origin.x)
      let y = clamp01(1 - box.origin.y - box.height)
      var w = clamp01(box.width)
      var h = clamp01(box.height)
      if x + w > 1 { w = max(0.0001, 1 - x) }
      if y + h > 1 { h = max(0.0001, 1 - y) }
      if w <= 0 || h <= 0 { continue }
      let confidence = min(1, max(0, Double(candidate.confidence)))
      blocks.append(
        ScreenOCRBlock(
          id: String(index),
          text: candidate.string,
          x: x, y: y, w: w, h: h,
          confidence: confidence))
      if !candidate.string.isEmpty { texts.append(candidate.string) }
    }
    guard !blocks.isEmpty else { return nil }
    return ScreenOCRAttachment(fullText: texts.joined(separator: "\n"), blocks: blocks)
  }

  private static func clamp01(_ value: CGFloat) -> Double {
    min(1, max(0, Double(value)))
  }
}
