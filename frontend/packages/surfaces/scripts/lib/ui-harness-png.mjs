import { deflateSync, inflateSync } from "node:zlib";
import { readFileSync, writeFileSync } from "node:fs";

export const CAPTURE_SUMMARY_SCHEMA = "omi.ui-harness.capture/v1";
export const DIFF_SUMMARY_SCHEMA = "omi.ui-harness.diff/v1";
export const DIFF_METHOD = "per-pixel-rgba-channel-tolerance-8";
export const DIFF_CHANNEL_TOLERANCE = 8;

const PNG_MAGIC = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function pngCrc(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function pngChunk(type, body) {
  const kind = Buffer.from(type);
  const payload = Buffer.concat([kind, body]);
  const chunk = Buffer.alloc(12 + body.length);
  chunk.writeUInt32BE(body.length, 0);
  payload.copy(chunk, 4);
  chunk.writeUInt32BE(pngCrc(payload), 8 + body.length);
  return chunk;
}

function paeth(left, above, upperLeft) {
  const estimate = left + above - upperLeft;
  const leftDistance = Math.abs(estimate - left);
  const aboveDistance = Math.abs(estimate - above);
  const upperLeftDistance = Math.abs(estimate - upperLeft);
  return leftDistance <= aboveDistance && leftDistance <= upperLeftDistance ? left : aboveDistance <= upperLeftDistance ? above : upperLeft;
}

export function encodeRgbaPng(width, height, rgba) {
  const stride = width * 4;
  if (rgba.length !== height * stride) throw new Error("RGBA buffer does not match dimensions");
  const rows = Buffer.alloc(height * (stride + 1));
  for (let row = 0; row < height; row += 1) {
    rgba.copy(rows, row * (stride + 1) + 1, row * stride, (row + 1) * stride);
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8;
  header[9] = 6;
  return Buffer.concat([
    PNG_MAGIC,
    pngChunk("IHDR", header),
    pngChunk("IDAT", deflateSync(rows, { level: 9 })),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

export function decodePngFile(file) {
  return decodePngBytes(readFileSync(file));
}

export function decodePngBytes(bytes) {
  if (bytes.length < 24 || !bytes.subarray(0, 8).equals(PNG_MAGIC) || bytes.toString("ascii", 12, 16) !== "IHDR") {
    throw new Error("not a PNG");
  }
  const width = bytes.readUInt32BE(16);
  const height = bytes.readUInt32BE(20);
  const bitDepth = bytes[24];
  const colorType = bytes[25];
  if (bitDepth !== 8 || bytes[26] !== 0 || bytes[27] !== 0 || bytes[28] !== 0) {
    throw new Error("PNG must be non-interlaced 8-bit");
  }
  if (colorType !== 2 && colorType !== 6) throw new Error("PNG must be RGB or RGBA");
  const channels = colorType === 6 ? 4 : 3;
  const idat = [];
  for (let offset = 8; offset + 12 <= bytes.length;) {
    const length = bytes.readUInt32BE(offset);
    const end = offset + 12 + length;
    if (end > bytes.length) throw new Error("truncated PNG chunk");
    if (bytes.toString("ascii", offset + 4, offset + 8) === "IDAT") idat.push(bytes.subarray(offset + 8, offset + 8 + length));
    offset = end;
  }
  if (idat.length === 0) throw new Error("PNG has no image data");
  const rowBytes = width * channels;
  const inflated = inflateSync(Buffer.concat(idat), { maxOutputLength: height * (rowBytes + 1) });
  if (inflated.length !== height * (rowBytes + 1)) throw new Error("unexpected PNG image data length");
  const previous = Buffer.alloc(rowBytes);
  const current = Buffer.alloc(rowBytes);
  const rgba = Buffer.alloc(height * width * 4);
  for (let row = 0; row < height; row += 1) {
    const inputOffset = row * (rowBytes + 1);
    const filter = inflated[inputOffset];
    if (filter > 4) throw new Error("unsupported PNG filter");
    for (let column = 0; column < rowBytes; column += 1) {
      const raw = inflated[inputOffset + 1 + column];
      const left = column >= channels ? current[column - channels] : 0;
      const above = previous[column];
      const upperLeft = column >= channels ? previous[column - channels] : 0;
      const predictor = filter === 1 ? left
        : filter === 2 ? above
        : filter === 3 ? Math.floor((left + above) / 2)
        : filter === 4 ? paeth(left, above, upperLeft)
        : 0;
      current[column] = (raw + predictor) & 0xff;
    }
    for (let x = 0; x < width; x += 1) {
      const src = x * channels;
      const dst = (row * width + x) * 4;
      rgba[dst] = current[src];
      rgba[dst + 1] = current[src + 1];
      rgba[dst + 2] = current[src + 2];
      rgba[dst + 3] = channels === 4 ? current[src + 3] : 255;
    }
    current.copy(previous);
  }
  return { width, height, rgba, bytes: bytes.length };
}

export function writePngFile(file, width, height, rgba) {
  writeFileSync(file, encodeRgbaPng(width, height, rgba));
}

export function pixelDelta(before, after, tolerance = DIFF_CHANNEL_TOLERANCE) {
  if (before.width !== after.width || before.height !== after.height) {
    const totalPixels = Math.max(before.width * before.height, after.width * after.height);
    return {
      changedPixels: totalPixels,
      totalPixels,
      delta: 1,
      dimensionMismatch: true,
    };
  }
  const totalPixels = before.width * before.height;
  let changedPixels = 0;
  for (let offset = 0; offset < before.rgba.length; offset += 4) {
    const red = Math.abs(before.rgba[offset] - after.rgba[offset]);
    const green = Math.abs(before.rgba[offset + 1] - after.rgba[offset + 1]);
    const blue = Math.abs(before.rgba[offset + 2] - after.rgba[offset + 2]);
    const alpha = Math.abs(before.rgba[offset + 3] - after.rgba[offset + 3]);
    if (Math.max(red, green, blue, alpha) > tolerance) changedPixels += 1;
  }
  return {
    changedPixels,
    totalPixels,
    delta: totalPixels === 0 ? 0 : changedPixels / totalPixels,
    dimensionMismatch: false,
  };
}

export function sideBySidePng(before, after) {
  const gap = 8;
  const width = before.width + gap + after.width;
  const height = Math.max(before.height, after.height);
  const rgba = Buffer.alloc(width * height * 4, 255);
  const blit = (image, originX) => {
    for (let y = 0; y < image.height; y += 1) {
      for (let x = 0; x < image.width; x += 1) {
        const src = (y * image.width + x) * 4;
        const dst = (y * width + originX + x) * 4;
        image.rgba.copy(rgba, dst, src, src + 4);
      }
    }
  };
  blit(before, 0);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < gap; x += 1) {
      const dst = (y * width + before.width + x) * 4;
      rgba[dst] = 255;
      rgba[dst + 1] = 0;
      rgba[dst + 2] = 128;
      rgba[dst + 3] = 255;
    }
  }
  blit(after, before.width + gap);
  return encodeRgbaPng(width, height, rgba);
}

export function isCaptureSummary(value) {
  return Boolean(
    value
    && value.schema === CAPTURE_SUMMARY_SCHEMA
    && (value.mode === "browser" || value.mode === "shell")
    && typeof value.outDir === "string"
    && Number.isFinite(value.wallClockMs)
    && Array.isArray(value.entries)
    && value.entries.every((entry) =>
      entry
      && typeof entry.id === "string"
      && typeof entry.url === "string"
      && (entry.skipped === true || Number.isInteger(entry.bytes))
      && entry.viewport
      && Number.isInteger(entry.viewport.width)
      && Number.isInteger(entry.viewport.height)
      && (entry.skipped === true || Number.isFinite(entry.renderMs))
      && Array.isArray(entry.consoleErrors)
    ),
  );
}

export function assertCaptureSummary(value, label = "capture summary") {
  if (!isCaptureSummary(value)) throw new Error(`${label} is not a valid ${CAPTURE_SUMMARY_SCHEMA} document`);
  return value;
}
