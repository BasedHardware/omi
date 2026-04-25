/**
 * Detect image MIME type from base64-encoded data by inspecting header bytes.
 * Extracted to a separate module to avoid importing index.ts side effects in tests.
 */
export function detectImageMimeType(base64Data: string): string {
  const header = Buffer.from(base64Data.slice(0, 24), "base64");
  // WebP: starts with RIFF....WEBP
  if (header.length >= 12 && header.slice(0, 4).toString("ascii") === "RIFF" && header.slice(8, 12).toString("ascii") === "WEBP") {
    return "image/webp";
  }
  // PNG: starts with 0x89 0x50 0x4E 0x47 0x0D 0x0A 0x1A 0x0A
  if (header.length >= 8 && header[0] === 0x89 && header[1] === 0x50 && header[2] === 0x4e && header[3] === 0x47 && header[4] === 0x0d && header[5] === 0x0a && header[6] === 0x1a && header[7] === 0x0a) {
    return "image/png";
  }
  // Default: JPEG
  return "image/jpeg";
}
