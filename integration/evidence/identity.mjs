import { createHash } from 'node:crypto';
import { readFile, stat } from 'node:fs/promises';

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const MIN_NONTRIVIAL_BYTES = 5 * 1024;

/**
 * @param {string} filePath
 * @returns {Promise<string>} hex sha256 of file contents
 */
export async function sha256File(filePath) {
  const data = await readFile(filePath);
  return createHash('sha256').update(data).digest('hex');
}

/**
 * Hard rule: byte-identical before/after evidence means the UI never
 * repainted — that is a failed run, not a pass.
 *
 * @param {string} beforePath
 * @param {string} afterPath
 */
export async function assertDistinct(beforePath, afterPath) {
  const beforeHash = await sha256File(beforePath);
  const afterHash = await sha256File(afterPath);
  if (beforeHash === afterHash) {
    throw new Error(
      `before/after evidence images are byte-identical (sha256 ${beforeHash}); ` +
        `the UI did not repaint — this is a failed run, not a pass`,
    );
  }
}

/**
 * Parse width/height/format from PNG IHDR chunk bytes. No shell-out.
 *
 * @param {string} filePath
 * @returns {Promise<{width: number, height: number, format: 'png'}>}
 */
export async function describeImage(filePath) {
  const data = await readFile(filePath);
  if (data.length < 24) {
    throw new Error(`file too short to be a PNG: ${filePath} (${data.length} bytes)`);
  }
  if (!data.subarray(0, 8).equals(PNG_SIGNATURE)) {
    throw new Error(`not a PNG (bad signature): ${filePath}`);
  }
  const length = data.readUInt32BE(8);
  const type = data.subarray(12, 16).toString('ascii');
  if (type !== 'IHDR' || length < 13) {
    throw new Error(`PNG missing IHDR chunk: ${filePath}`);
  }
  const width = data.readUInt32BE(16);
  const height = data.readUInt32BE(20);
  return { width, height, format: 'png' };
}

/**
 * Fail on zero-byte, absurdly small (<5KB), or 1×1 images.
 *
 * @param {string} filePath
 */
export async function assertNonTrivial(filePath) {
  const info = await stat(filePath);
  if (info.size === 0) {
    throw new Error(`evidence image is empty (0 bytes): ${filePath}`);
  }
  if (info.size < MIN_NONTRIVIAL_BYTES) {
    throw new Error(
      `evidence image is absurdly small (${info.size} bytes < ${MIN_NONTRIVIAL_BYTES}): ${filePath}`,
    );
  }
  const image = await describeImage(filePath);
  if (image.width === 1 && image.height === 1) {
    throw new Error(`evidence image is 1×1 (placeholder, not a real capture): ${filePath}`);
  }
}
