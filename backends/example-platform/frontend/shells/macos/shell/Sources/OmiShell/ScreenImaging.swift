import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

enum ScreenImaging {
  static let previewLongEdge = 80
  static let captureLongEdge = 3_000

  static func clampLongEdge(_ image: CGImage, maxLongEdge: Int) -> CGImage {
    let width = image.width
    let height = image.height
    let longEdge = max(width, height)
    guard longEdge > maxLongEdge, longEdge > 0 else { return image }
    let scale = CGFloat(maxLongEdge) / CGFloat(longEdge)
    let outW = max(1, Int((CGFloat(width) * scale).rounded()))
    let outH = max(1, Int((CGFloat(height) * scale).rounded()))
    return resize(image, width: outW, height: outH) ?? image
  }

  static func dhash64(_ image: CGImage) -> UInt64 {
    let preview = clampLongEdge(image, maxLongEdge: previewLongEdge)
    guard let gray = grayscale9x8(preview) else { return 0 }
    return ScreenDHash.hash64(gray9x8: gray)
  }

  static func grayscale9x8(_ image: CGImage) -> [UInt8]? {
    let width = 9
    let height = 8
    var pixels = [UInt8](repeating: 0, count: width * height)
    let ok = pixels.withUnsafeMutableBytes { raw -> Bool in
      guard let ctx = CGContext(
        data: raw.baseAddress,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: width,
        space: CGColorSpaceCreateDeviceGray(),
        bitmapInfo: CGImageAlphaInfo.none.rawValue
      ) else { return false }
      ctx.interpolationQuality = .high
      ctx.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
      return true
    }
    return ok ? pixels : nil
  }

  static func resize(_ image: CGImage, width: Int, height: Int) -> CGImage? {
    guard let ctx = CGContext(
      data: nil,
      width: width,
      height: height,
      bitsPerComponent: 8,
      bytesPerRow: 0,
      space: image.colorSpace ?? CGColorSpaceCreateDeviceRGB(),
      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ) else { return nil }
    ctx.interpolationQuality = .high
    ctx.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
    return ctx.makeImage()
  }

  static func pngData(_ image: CGImage) -> Data? {
    let data = NSMutableData()
    guard let dest = CGImageDestinationCreateWithData(
      data, UTType.png.identifier as CFString, 1, nil)
    else { return nil }
    CGImageDestinationAddImage(dest, image, nil)
    guard CGImageDestinationFinalize(dest) else { return nil }
    return data as Data
  }

  static func pngBase64(_ image: CGImage, maxLongEdge: Int?) -> (String, Int, Int)? {
    let scaled: CGImage
    if let maxLongEdge {
      scaled = clampLongEdge(image, maxLongEdge: maxLongEdge)
    } else {
      scaled = image
    }
    guard let data = pngData(scaled) else { return nil }
    return (data.base64EncodedString(), scaled.width, scaled.height)
  }
}
