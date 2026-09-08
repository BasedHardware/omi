import { describe, expect, it } from "vitest";
import { detectImageMimeType } from "../src/mime-detect.js";

/**
 * Unit tests for detectImageMimeType — verifies that base64-encoded images
 * are correctly identified by their header bytes.
 *
 * This was extracted after PR #6633 shipped with hardcoded "image/jpeg" for
 * screenshots that ScreenCaptureManager actually encodes as WebP, causing
 * Anthropic API 400: "image was specified using image/jpeg media type, but
 * the image appears to be a image/webp image".
 */

// Helper: encode raw bytes to base64
function bytesToBase64(bytes: number[]): string {
  return Buffer.from(bytes).toString("base64");
}

describe("detectImageMimeType", () => {
  it("detects WebP from RIFF....WEBP header", () => {
    // Real WebP header: RIFF + 4-byte size + WEBP
    const webpHeader = [
      0x52, 0x49, 0x46, 0x46, // RIFF
      0x00, 0x00, 0x10, 0x00, // file size (arbitrary)
      0x57, 0x45, 0x42, 0x50, // WEBP
      0x56, 0x50, 0x38, 0x20, // VP8 chunk (padding)
    ];
    expect(detectImageMimeType(bytesToBase64(webpHeader))).toBe("image/webp");
  });

  it("detects PNG from full 8-byte magic", () => {
    // PNG magic: 89 50 4E 47 0D 0A 1A 0A
    const pngHeader = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d];
    expect(detectImageMimeType(bytesToBase64(pngHeader))).toBe("image/png");
  });

  it("falls back to JPEG for JPEG SOI header", () => {
    // JPEG starts with FF D8 FF
    const jpegHeader = [0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01];
    expect(detectImageMimeType(bytesToBase64(jpegHeader))).toBe("image/jpeg");
  });

  it("falls back to JPEG for unknown/arbitrary bytes", () => {
    const randomBytes = [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b];
    expect(detectImageMimeType(bytesToBase64(randomBytes))).toBe("image/jpeg");
  });

  it("falls back to JPEG for empty string", () => {
    expect(detectImageMimeType("")).toBe("image/jpeg");
  });

  it("falls back to JPEG for very short base64", () => {
    // Only 1 byte decoded — too short for any signature
    expect(detectImageMimeType("AA==")).toBe("image/jpeg");
  });

  it("does not misidentify partial PNG (only 0x89 0x50, not full 8 bytes)", () => {
    // Only first 2 bytes match PNG but rest doesn't — should NOT be PNG
    const partialPng = [0x89, 0x50, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00];
    expect(detectImageMimeType(bytesToBase64(partialPng))).toBe("image/jpeg");
  });

  it("falls back to JPEG for malformed non-base64 input", () => {
    // Garbage string that isn't valid base64
    expect(detectImageMimeType("not-base64-at-all!!!")).toBe("image/jpeg");
  });

  it("does not misidentify RIFF without WEBP marker", () => {
    // RIFF header but with AVI instead of WEBP
    const aviHeader = [
      0x52, 0x49, 0x46, 0x46, // RIFF
      0x00, 0x00, 0x10, 0x00, // size
      0x41, 0x56, 0x49, 0x20, // AVI (not WEBP)
    ];
    expect(detectImageMimeType(bytesToBase64(aviHeader))).toBe("image/jpeg");
  });
});
