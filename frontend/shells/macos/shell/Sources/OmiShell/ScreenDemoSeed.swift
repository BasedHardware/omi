import CoreGraphics
import Foundation

/// Device-local pixels for the demo persona's opaque frame refs.
///
/// The service seed cannot own HEVC bytes: pixels stay on this side of
/// `FORBIDDEN_PIXEL_KEYS`. Live ingest uses opaque refs, so the seed does too.
/// These images are a generated test pattern, not a captured display.
enum ScreenDemoSeed {
  static let harborlineId = "demo-screen-harborline-reservation"
  static let cedarId = "demo-screen-cedar-packing"
  static let fableId = "demo-screen-fable-wick-sketch"

  static var knownIds: Set<String> {
    [harborlineId, cedarId, fableId]
  }

  static func plantIfKnown(store: ScreenLocalStore, frameRef: String) throws -> Bool {
    guard knownIds.contains(frameRef) else { return false }
    if store.row(frameRef: frameRef) != nil {
      do {
        _ = try store.decodeFrame(frameRef: frameRef, maxLongEdge: 64)
        return true
      } catch {
        // An index hit is not enough: a relaunch that reused chunk-000001
        // can leave this ref pointing at an empty file. Drop and replant.
        store.dropFrame(frameRef: frameRef)
      }
    }
    let image = syntheticImage(for: frameRef)
    let dhash = ScreenDHash.hex(ScreenImaging.dhash64(image))
    _ = try store.appendFrame(
      image: image,
      capturedAt: Date(),
      appBundleId: "me.omi.demo.seed",
      appName: "Demo seed",
      windowTitle: frameRef,
      dhash: dhash,
      ocr: nil,
      allowWrite: true,
      frameRef: frameRef)
    store.finishWriter()
    return true
  }

  static func syntheticImage(for frameRef: String) -> CGImage {
    let width = 320
    let height = 180
    let color = color(for: frameRef)
    let bytesPerPixel = 4
    let bytesPerRow = width * bytesPerPixel
    var pixels = [UInt8](repeating: 0, count: height * bytesPerRow)
    for y in 0..<height {
      for x in 0..<width {
        let band = x < width / 3 || (x > width / 2 && y < height / 2)
        let i = y * bytesPerRow + x * bytesPerPixel
        pixels[i] = band ? color.b : 0x20
        pixels[i + 1] = band ? color.g : 0x20
        pixels[i + 2] = band ? color.r : 0x20
        pixels[i + 3] = 0xff
      }
    }
    return pixels.withUnsafeMutableBytes { raw in
      let ctx = CGContext(
        data: raw.baseAddress,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: bytesPerRow,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue
          | CGBitmapInfo.byteOrder32Little.rawValue)!
      return ctx.makeImage()!
    }
  }

  private static func color(for frameRef: String) -> (r: UInt8, g: UInt8, b: UInt8) {
    switch frameRef {
    case harborlineId: return (0x12, 0x9a, 0x8a)
    case cedarId: return (0xd9, 0x7a, 0x1c)
    default: return (0x6b, 0x4c, 0xc4)
    }
  }
}
