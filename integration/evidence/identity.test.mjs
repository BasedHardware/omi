import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, copyFile, readFile, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import {
  sha256File,
  assertDistinct,
  describeImage,
  assertNonTrivial,
} from './identity.mjs';

/**
 * Build a minimal PNG buffer with the given IHDR dimensions.
 * Only signature + IHDR are required for describeImage; CRC is computed
 * so the chunk is structurally honest.
 */
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? (0xedb88320 ^ (c >>> 1)) : c >>> 1;
    }
  }
  return (c ^ 0xffffffff) >>> 0;
}

function buildPng({ width, height }) {
  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const ihdrData = Buffer.alloc(13);
  ihdrData.writeUInt32BE(width, 0);
  ihdrData.writeUInt32BE(height, 4);
  ihdrData[8] = 8; // bit depth
  ihdrData[9] = 2; // color type RGB
  ihdrData[10] = 0;
  ihdrData[11] = 0;
  ihdrData[12] = 0;
  const type = Buffer.from('IHDR');
  const len = Buffer.alloc(4);
  len.writeUInt32BE(13, 0);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([type, ihdrData])), 0);
  return Buffer.concat([signature, len, type, ihdrData, crc]);
}

async function tempDir() {
  return mkdtemp(path.join(tmpdir(), 'omi-evidence-identity-'));
}

describe('identity.sha256File', () => {
  // red-proof: return a constant hash string instead of hashing file bytes
  it('hashes file contents — identical bytes share a digest, mutated bytes diverge', async () => {
    const dir = await tempDir();
    const a = path.join(dir, 'a.bin');
    const b = path.join(dir, 'b.bin');
    const c = path.join(dir, 'c.bin');
    await writeFile(a, Buffer.from('evidence-body-v1'));
    await writeFile(b, Buffer.from('evidence-body-v1'));
    await writeFile(c, Buffer.from('evidence-body-v2'));

    const ha = await sha256File(a);
    const hb = await sha256File(b);
    const hc = await sha256File(c);

    assert.equal(ha, hb);
    assert.notEqual(ha, hc);
    assert.match(ha, /^[0-9a-f]{64}$/);
  });
});

describe('identity.assertDistinct', () => {
  // red-proof: delete the hash-equality throw so identical before/after silently returns
  it('throws in plain language when before and after are byte-identical copies', async () => {
    const dir = await tempDir();
    const before = path.join(dir, 'before.png');
    const after = path.join(dir, 'after.png');
    const png = buildPng({ width: 8, height: 8 });
    await writeFile(before, png);
    await copyFile(before, after);

    await assert.rejects(
      () => assertDistinct(before, after),
      (err) => {
        assert.ok(err instanceof Error);
        assert.match(err.message, /byte-identical/i);
        assert.match(err.message, /did not repaint|failed run/i);
        return true;
      },
    );
  });

  // red-proof: throw unconditionally even when hashes differ
  it('resolves when before and after hashes differ', async () => {
    const dir = await tempDir();
    const before = path.join(dir, 'before.png');
    const after = path.join(dir, 'after.png');
    await writeFile(before, buildPng({ width: 8, height: 8 }));
    await writeFile(after, buildPng({ width: 16, height: 9 }));
    await assertDistinct(before, after);
  });
});

describe('identity.describeImage', () => {
  // red-proof: hardcode {width:1,height:1,format:'png'} instead of reading IHDR BE fields
  it('returns the true pixel dimensions of a PNG constructed byte-by-byte', async () => {
    const dir = await tempDir();
    const file = path.join(dir, 'probe.png');
    // 37×19 is an arbitrary non-square size no stub would guess.
    const width = 37;
    const height = 19;
    const png = buildPng({ width, height });

    // Sanity: IHDR width/height live at absolute offsets 16 and 20.
    assert.equal(png.readUInt32BE(16), width);
    assert.equal(png.readUInt32BE(20), height);

    await writeFile(file, png);
    const desc = await describeImage(file);
    assert.deepEqual(desc, { width: 37, height: 19, format: 'png' });
  });

  // red-proof: skip the signature check
  it('rejects non-PNG bytes', async () => {
    const dir = await tempDir();
    const file = path.join(dir, 'not.png');
    // ≥24 bytes so length gate is cleared and signature check is what fires.
    await writeFile(file, Buffer.from('JFIF-not-a-png!!!!!!!!!!!!'));
    await assert.rejects(() => describeImage(file), /not a PNG|bad signature/i);
  });
});

describe('identity.assertNonTrivial', () => {
  // red-proof: remove the zero-byte size check
  it('rejects a zero-byte file', async () => {
    const dir = await tempDir();
    const file = path.join(dir, 'empty.png');
    await writeFile(file, Buffer.alloc(0));
    await assert.rejects(() => assertNonTrivial(file), /empty|0 bytes/i);
  });

  // red-proof: raise the minimum-size threshold gate so a 100-byte file passes
  it('rejects an absurdly small (<5KB) image even with valid IHDR', async () => {
    const dir = await tempDir();
    const file = path.join(dir, 'tiny.png');
    await writeFile(file, buildPng({ width: 64, height: 64 }));
    const bytes = (await readFile(file)).length;
    assert.ok(bytes < 5 * 1024, `fixture must be <5KB, got ${bytes}`);
    await assert.rejects(() => assertNonTrivial(file), /absurdly small/i);
  });

  // red-proof: delete the 1×1 dimension rejection
  it('rejects a 1×1 image even when padded above 5KB', async () => {
    const dir = await tempDir();
    const file = path.join(dir, 'one-by-one.png');
    const header = buildPng({ width: 1, height: 1 });
    const padded = Buffer.concat([header, Buffer.alloc(6 * 1024, 0x00)]);
    await writeFile(file, padded);
    await assert.rejects(() => assertNonTrivial(file), /1×1|1x1/i);
  });

  // red-proof: throw on every call regardless of size/dimensions
  it('accepts a >=5KB image with non-1×1 dimensions', async () => {
    const dir = await tempDir();
    await mkdir(dir, { recursive: true });
    const file = path.join(dir, 'real.png');
    const header = buildPng({ width: 320, height: 240 });
    const padded = Buffer.concat([header, Buffer.alloc(6 * 1024, 0xab)]);
    await writeFile(file, padded);
    await assertNonTrivial(file);
  });
});
