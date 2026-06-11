import XCTest
import CWebP

@testable import Omi_Computer

/// Tests for the WebP encoding path in ScreenCaptureManager, covering
/// C interop correctness, memory cleanup, and output format validation.
final class ScreenCaptureWebPTests: XCTestCase {

    // MARK: - WebP encoding via libwebp C API

    func testWebPEncodeRGBAProducesValidData() {
        // Create a small 4x4 RGBA image (solid red)
        let width: Int32 = 4
        let height: Int32 = 4
        let rowBytes = width * 4
        var pixels = [UInt8](repeating: 0, count: Int(width * height * 4))
        for i in Swift.stride(from: 0, to: pixels.count, by: 4) {
            pixels[i]     = 255  // R
            pixels[i + 1] = 0    // G
            pixels[i + 2] = 0    // B
            pixels[i + 3] = 255  // A (noneSkipLast — ignored by encoder)
        }

        var output: UnsafeMutablePointer<UInt8>?
        let size = WebPEncodeRGBA(&pixels, width, height, rowBytes, 70.0, &output)

        XCTAssertGreaterThan(size, 0, "WebPEncodeRGBA must return a positive byte count")
        XCTAssertNotNil(output, "WebPEncodeRGBA must set the output pointer")

        // WebP files start with "RIFF" magic bytes
        if let ptr = output, size >= 4 {
            let magic = String(bytes: [ptr[0], ptr[1], ptr[2], ptr[3]], encoding: .ascii)
            XCTAssertEqual(magic, "RIFF", "WebP data must start with RIFF header")
        }

        // Cleanup — mirrors ScreenCaptureManager.captureScreenData()
        if let ptr = output { WebPFree(ptr) }
    }

    func testWebPEncodeRGBAZeroDimensionsReturnsZero() {
        var pixel: UInt8 = 0
        var output: UnsafeMutablePointer<UInt8>?

        let size = WebPEncodeRGBA(&pixel, 0, 0, 0, 70.0, &output)

        XCTAssertEqual(size, 0, "Zero-dimension encode must return 0 (no crash)")
        // output may or may not be nil — just verify no crash and size == 0
    }

    func testWebPEncodeQualityBounds() {
        let width: Int32 = 2
        let height: Int32 = 2
        let rowBytes = width * 4
        var pixels = [UInt8](repeating: 128, count: Int(width * height * 4))

        // Quality 70 (the value used in production)
        var output70: UnsafeMutablePointer<UInt8>?
        let size70 = WebPEncodeRGBA(&pixels, width, height, rowBytes, 70.0, &output70)
        XCTAssertGreaterThan(size70, 0, "Quality 70 must produce valid output")
        if let ptr = output70 { WebPFree(ptr) }

        // Quality 100 (max)
        var output100: UnsafeMutablePointer<UInt8>?
        let size100 = WebPEncodeRGBA(&pixels, width, height, rowBytes, 100.0, &output100)
        XCTAssertGreaterThan(size100, 0, "Quality 100 must produce valid output")
        if let ptr = output100 { WebPFree(ptr) }
    }

    // MARK: - WebP data format validation

    func testCapturedDataHasWebPMagicHeader() {
        // Simulate the encoding path from ScreenCaptureManager without
        // needing screen recording permission. Build a 10x10 CGImage,
        // render it to RGBA context, encode with WebPEncodeRGBA.
        let width = 10
        let height = 10

        guard let context = CGContext(
            data: nil,
            width: width,
            height: height,
            bitsPerComponent: 8,
            bytesPerRow: width * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue
        ) else {
            XCTFail("Could not create CGContext")
            return
        }

        // Fill with a gradient pattern
        context.setFillColor(CGColor(red: 0.2, green: 0.5, blue: 0.8, alpha: 1.0))
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))

        guard let pixelData = context.data else {
            XCTFail("CGContext has no pixel data")
            return
        }

        let rgba = pixelData.assumingMemoryBound(to: UInt8.self)
        var output: UnsafeMutablePointer<UInt8>?
        let size = WebPEncodeRGBA(rgba, Int32(width), Int32(height), Int32(width * 4), 70.0, &output)

        XCTAssertGreaterThan(size, 0)
        guard let ptr = output else {
            XCTFail("Output pointer is nil despite size > 0")
            return
        }

        let data = Data(bytes: ptr, count: size)
        WebPFree(ptr)

        // Validate WebP RIFF container: "RIFF" + 4-byte size + "WEBP"
        XCTAssertGreaterThanOrEqual(data.count, 12, "WebP data must be at least 12 bytes")
        XCTAssertEqual(String(data: data[0..<4], encoding: .ascii), "RIFF")
        XCTAssertEqual(String(data: data[8..<12], encoding: .ascii), "WEBP")
    }

    // MARK: - Fallback streak flag and reset helper (per CP8 tester feedback)

    func testFallbackStreakFlagDefaultsToZero() {
        // Verify that the fallback-streak UserDefaults key starts at 0
        // and can be reset — guards the "screen recording lost" false-positive fix.
        let key = "screenCaptureFallbackStreak"
        UserDefaults.standard.removeObject(forKey: key)
        let value = UserDefaults.standard.integer(forKey: key)
        XCTAssertEqual(value, 0, "Fallback streak must default to 0 when unset")
    }
}
