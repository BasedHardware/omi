//
//  MeetingBannerPalette.swift — the two colours a banner is built on, and when to admit there are none.
//
//  The banner is a *designed* header with the approved frame as a small inset, not the frame blown
//  up. That decision is measured, not aesthetic: 1,690 of 2,061 real frames came from Claude Code,
//  Cursor, ChatGPT or Chrome, and dense text cropped to a wide banner is grey noise. So the frame's
//  job here is to lend the header its hue, and everything else is ours.
//
//  Which makes hue extraction the whole game, and the obvious implementation is wrong twice:
//
//  1. **A mean over hues returns mud.** Hue is circular, so averaging a diff's reds and greens, or
//     a browser's blue chrome against an amber warning, lands on something that was never in the
//     picture. This takes the *mode* — the heaviest bin of a 24-bin histogram — and only then
//     refines it by a circular mean of the members of that one bin.
//  2. **Most screenshots have no hue at all.** A terminal, a plain document, a black editor: those
//     are achromatic, and a mean over their noise still yields *some* angle, so the banner gets a
//     confident arbitrary colour with nothing behind it. Below a weight floor this says so and the
//     caller uses a neutral slate instead of inventing one.
//
//  The pure entry point takes bytes rather than an `NSImage` so the arithmetic is testable without
//  a window server, and so nothing non-`Sendable` has to cross an isolation boundary to reach it.
//

import CoreGraphics
import Foundation

#if canImport(AppKit)
  import AppKit
#endif

/// A banner ground, and whether the picture actually earned it.
struct MeetingBannerGround: Equatable, Sendable {
  /// Top-leading and bottom-trailing stops of the gradient, as HSB triples.
  let stops: [HSB]
  /// True when the frame carried no usable colour and these stops are the neutral fallback.
  let isNeutral: Bool

  struct HSB: Equatable, Sendable {
    let hue: Double
    let saturation: Double
    let brightness: Double
  }
}

enum MeetingBannerPalette {

  // MARK: - Tuning

  /// 24 bins ≈ 15° each: fine enough to separate a blue chrome from a green diff, coarse enough
  /// that antialiasing around text does not split one real colour across two bins.
  static let binCount = 24

  /// Below this, the frame is achromatic and any hue would be invented. Scaled per sample so it is
  /// independent of the sampling grid.
  static let chromaFloorPerSample = 0.045

  /// White body text must clear this against the *lighter* stop. 4.5:1 is the WCAG AA threshold for
  /// normal text; the title is large but it also sits over a photograph-adjacent gradient, so the
  /// stricter number is the right one to hold.
  static let minimumContrastForWhite = 4.5

  // MARK: - Pure core

  /// Derive a ground from raw RGBA8 samples.
  ///
  /// - Parameters:
  ///   - rgba: premultiplied-last RGBA bytes, four per sample.
  static func ground(fromRGBA rgba: [UInt8]) -> MeetingBannerGround {
    guard rgba.count >= 4 else { return neutral }
    let sampleCount = rgba.count / 4

    var bins = [Double](repeating: 0, count: binCount)
    var binX = [Double](repeating: 0, count: binCount)
    var binY = [Double](repeating: 0, count: binCount)
    var totalWeight = 0.0

    for i in stride(from: 0, to: sampleCount * 4, by: 4) {
      let r = Double(rgba[i]) / 255
      let g = Double(rgba[i + 1]) / 255
      let b = Double(rgba[i + 2]) / 255
      let (hue, saturation, brightness) = hsb(r: r, g: g, b: b)

      // Weight by chroma, and discount both ends of the brightness range. Near-white paper and
      // near-black editor chrome are the two most common things on this user's screen and neither
      // says anything about the meeting.
      let midness = 1 - abs(brightness - 0.5) * 2
      let weight = saturation * saturation * max(0, midness)
      guard weight > 0 else { continue }

      let bin = min(binCount - 1, Int(hue * Double(binCount)))
      bins[bin] += weight
      let radians = hue * 2 * .pi
      binX[bin] += cos(radians) * weight
      binY[bin] += sin(radians) * weight
      totalWeight += weight
    }

    guard totalWeight >= chromaFloorPerSample * Double(sampleCount),
      let winner = bins.indices.max(by: { bins[$0] < bins[$1] }), bins[winner] > 0
    else { return neutral }

    // Circular mean *within* the winning bin only — precision without letting an unrelated hue on
    // the other side of the wheel drag the answer.
    var hue = atan2(binY[winner], binX[winner]) / (2 * .pi)
    if hue < 0 { hue += 1 }

    return MeetingBannerGround(stops: stops(forHue: hue), isNeutral: false)
  }

  /// The ground for a frame with no colour of its own: Omi's neutral slate, not a random angle.
  static let neutral = MeetingBannerGround(
    stops: [
      .init(hue: 0.62, saturation: 0.12, brightness: 0.40),
      .init(hue: 0.62, saturation: 0.16, brightness: 0.24),
    ],
    isNeutral: true)

  /// Two stops at a fixed saturation, darkened until white text clears AA contrast on the lighter
  /// one. Yellows and cyans are much brighter than blues at identical HSB brightness, so a constant
  /// is not good enough here — this measures rather than assumes.
  static func stops(forHue hue: Double) -> [MeetingBannerGround.HSB] {
    var brightness = 0.46
    let saturation = 0.42
    while brightness > 0.16,
      contrastWithWhite(hue: hue, saturation: saturation, brightness: brightness)
        < minimumContrastForWhite
    {
      brightness -= 0.02
    }
    let secondHue = (hue + 0.06).truncatingRemainder(dividingBy: 1)
    return [
      .init(hue: hue, saturation: saturation, brightness: brightness),
      .init(hue: secondHue, saturation: saturation + 0.13, brightness: max(0.12, brightness - 0.18)),
    ]
  }

  // MARK: - Colour arithmetic

  static func contrastWithWhite(hue: Double, saturation: Double, brightness: Double) -> Double {
    let (r, g, b) = rgb(h: hue, s: saturation, v: brightness)
    let luminance = relativeLuminance(r: r, g: g, b: b)
    return 1.05 / (luminance + 0.05)
  }

  static func relativeLuminance(r: Double, g: Double, b: Double) -> Double {
    func channel(_ c: Double) -> Double {
      c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
  }

  static func hsb(r: Double, g: Double, b: Double) -> (Double, Double, Double) {
    let maximum = max(r, g, b)
    let minimum = min(r, g, b)
    let delta = maximum - minimum
    var hue = 0.0
    if delta > 0 {
      if maximum == r {
        hue = ((g - b) / delta).truncatingRemainder(dividingBy: 6)
      } else if maximum == g {
        hue = (b - r) / delta + 2
      } else {
        hue = (r - g) / delta + 4
      }
      hue /= 6
      if hue < 0 { hue += 1 }
    }
    return (hue, maximum == 0 ? 0 : delta / maximum, maximum)
  }

  static func rgb(h: Double, s: Double, v: Double) -> (Double, Double, Double) {
    if s <= 0 { return (v, v, v) }
    let sector = (h.truncatingRemainder(dividingBy: 1)) * 6
    let index = Int(sector)
    let f = sector - Double(index)
    let p = v * (1 - s)
    let q = v * (1 - s * f)
    let t = v * (1 - s * (1 - f))
    switch index % 6 {
    case 0: return (v, t, p)
    case 1: return (q, v, p)
    case 2: return (p, v, t)
    case 3: return (p, q, v)
    case 4: return (t, p, v)
    default: return (v, p, q)
    }
  }

  // MARK: - AppKit bridge

  #if canImport(AppKit)
    /// Sample a frame down to a 16x16 grid and derive its ground.
    ///
    /// 16x16 rather than 8x8: a 256-sample grid still costs nothing and it stops a single accent
    /// button in a corner from carrying a whole bin on its own.
    @MainActor
    static func ground(from image: NSImage) -> MeetingBannerGround {
      guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return neutral
      }
      let side = 16
      var pixels = [UInt8](repeating: 0, count: side * side * 4)
      guard
        let context = CGContext(
          data: &pixels, width: side, height: side, bitsPerComponent: 8,
          bytesPerRow: side * 4, space: CGColorSpaceCreateDeviceRGB(),
          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
      else { return neutral }
      context.interpolationQuality = .medium
      context.draw(cg, in: CGRect(x: 0, y: 0, width: side, height: side))
      return ground(fromRGBA: pixels)
    }
  #endif
}
