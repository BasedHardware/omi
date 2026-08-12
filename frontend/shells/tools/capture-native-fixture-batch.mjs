#!/usr/bin/env node
/**
 * Capture a bounded batch of screenshot-only native fixture coordinates.
 *
 * The matrix is the authority: this command does not invent coordinates,
 * resize devices, or turn AX/keyboard rows into screenshots. It builds each
 * shell once, then relaunches that exact scratch artifact sequentially. Every
 * image receives an atomic coordinate sidecar; a deterministic batch-result
 * manifest is written only after every requested coordinate succeeds. A
 * separate coordinator assembles the time-bound ledger receipt afterward.
 */
import { createHash, randomBytes } from "node:crypto";
import {
  existsSync,
  copyFileSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { deflateSync, inflateSync } from "node:zlib";

const coreRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const validDomains = new Set(["memories", "tasks", "conversations", "folders", "listen", "chat", "settings"]);
const validStates = new Set(["loading", "empty", "ready", "error", "offline", "busy", "complete", "cancelled"]);
const validThemes = new Set(["light", "dark"]);
const validWidths = new Set(["compact", "regular", "wide"]);
// Screenshot rows carry no AX/keyboard semantics.  Those rows are captured by
// their own evidence producers; accepting them here would overclaim what a
// pixel artifact proves.
const validAccessibilities = new Set(["none"]);
const validShells = new Set(["macos", "ios"]);
const validOrientations = new Set(["portrait", "landscape"]);
const fullSha = /^[0-9a-f]{40}$/;
const hex64 = /^[0-9a-f]{64}$/;
const safeRunId = /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/;
const safeLocale = /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$/;
const maxCoordinates = 1236;
const maxBatchCoordinates = 32;
const widthPolicy = {
  macos: {
    compact: { width: 760, height: 671, scale: 2, orientation: "landscape" },
    regular: { width: 960, height: 671, scale: 2, orientation: "landscape" },
    wide: { width: 1280, height: 800, scale: 2, orientation: "landscape" },
  },
  ios: {
    compact: { width: 402, height: 874, scale: 3, orientation: "portrait" },
    regular: { width: 820, height: 1180, scale: 2, orientation: "portrait" },
    // Current managed iPad Pro 13-inch simulators expose a native 1032x1376
    // logical portrait mode. It clears the shared-core wide breakpoint without
    // requiring an unobservable Simulator.app rotation side effect.
    wide: { width: 1032, height: 1376, scale: 2, orientation: "portrait" },
  },
};
const fixturePolicy = {
  memories: { loading: "loading", empty: "empty", ready: "normal", error: "unavailable", offline: "degraded", busy: "paged" },
  tasks: { loading: "loading", empty: "empty", ready: "normal", error: "unavailable", offline: "saved-failed", busy: "sending", complete: "complete" },
  conversations: { loading: "loading", empty: "empty", ready: "normal", error: "unavailable", offline: "saved-failed", busy: "sending" },
  folders: { loading: "polish:loading", empty: "polish:empty", ready: "polish:ready", error: "polish:error", offline: "polish:offline" },
  chat: { loading: "loading", empty: "empty", ready: "ready", error: "unavailable", offline: "saved-failed", busy: "streaming", complete: "normal", cancelled: "cancelled" },
  listen: { loading: "polish:loading", empty: "polish:empty", ready: "polish:ready", error: "polish:error", offline: "polish:offline", busy: "polish:busy", complete: "polish:complete" },
  settings: { loading: "loading", empty: "signed-out", ready: "signed-in", error: "unavailable", offline: "saving-failed" },
};

function fail(message) {
  throw new Error(message);
}

function parseArgs(argv) {
  const result = {};
  const flags = new Set(["dry_run", "replay_proof", "prepare", "assemble_receipt"]);
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) fail(`unexpected argument '${token}'`);
    const key = token.slice(2).replaceAll("-", "_");
    if (key === "help") return { help: true };
    if (flags.has(key)) {
      if (result[key]) fail(`--${key.replaceAll("_", "-")} may appear once`);
      result[key] = true;
      continue;
    }
    const value = argv[++i];
    if (!value || value.startsWith("--")) fail(`--${key.replaceAll("_", "-")} needs a value`);
    if (result[key] !== undefined) fail(`--${key.replaceAll("_", "-")} may appear once`);
    result[key] = value;
  }
  return result;
}

function usage() {
  return "usage: capture-native-fixture-batch.mjs --manifest matrix.json --out-root /scratch/out [--shell macos|ios|both] [--offset N] [--limit N] [--prepare | --prepared-input-set FILE] [--assemble-receipt --result-path FILE --started-at ISO --finished-at ISO --stdout-file FILE --stderr-file FILE] [--replay-proof] [--dry-run]";
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function canonicalBatchId(inputSetId, command, members) {
  return `batch-v1-${sha256(canonical({ command, input_set_id: inputSetId, members }))}`;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function hashFile(file) {
  return sha256(readFileSync(file));
}

function currentCoreSha(manifestSha) {
  const result = spawnSync("git", ["-C", coreRoot, "rev-parse", "HEAD"], { encoding: "utf8" });
  if (result.status === 0) {
    const sha = result.stdout.trim();
    if (!fullSha.test(sha)) fail("current core SHA is not a full SHA");
    return sha;
  }
  // Strict verifier replay copies the bound input files into a source-safe
  // scratch authority and intentionally does not expose .git metadata. The
  // manifest itself is an immutable input-set member and is checked against
  // the candidate's exact source revision before replay, so it is the only
  // trustworthy fallback when Git is unavailable in that copied authority.
  if (fullSha.test(manifestSha || "")) return manifestSha;
  fail("unable to resolve current core SHA");
}

function corePath(value, label) {
  if (!value || typeof value !== "string") fail(`${label} is required`);
  return path.isAbsolute(value) ? path.resolve(value) : path.resolve(coreRoot, value);
}

function ensureExistingDirectory(value, label) {
  if (!value || !path.isAbsolute(value)) fail(`${label} must be an absolute path`);
  const resolved = corePath(value, label);
  if (!existsSync(resolved) || !lstatSync(resolved).isDirectory()) fail(`${label} must be an existing directory`);
  return realpathSync(resolved);
}

function ensureOutputRoot(value) {
  const resolved = corePath(value, "--out-root");
  const parent = path.dirname(resolved);
  if (!existsSync(parent) || !lstatSync(parent).isDirectory()) fail("--out-root parent must already exist");
  if (existsSync(resolved) && lstatSync(resolved).isSymbolicLink()) fail("--out-root must not be a symlink");
  const authorityRoot = realpathSync(coreRoot);
  const realParent = realpathSync(parent);
  const lexical = path.resolve(realParent, path.basename(resolved));
  if (lexical !== authorityRoot && !lexical.startsWith(`${authorityRoot}${path.sep}`)) fail("--out-root must remain under the core authority root");
  mkdirSync(resolved, { recursive: true });
  return resolved;
}

function ensureManifestPath(value) {
  const resolved = corePath(value, "--manifest");
  if (!existsSync(resolved) || !lstatSync(resolved).isFile() || lstatSync(resolved).isSymbolicLink()) fail("--manifest must be a regular file");
  const authorityRoot = realpathSync(coreRoot);
  const realPath = realpathSync(resolved);
  if (realPath !== authorityRoot && !realPath.startsWith(`${authorityRoot}${path.sep}`)) fail("--manifest must remain under the core authority root");
  return realPath;
}

function ensurePreparedPath(value) {
  const resolved = corePath(value, "--prepared-input-set");
  if (!existsSync(resolved) || !lstatSync(resolved).isFile() || lstatSync(resolved).isSymbolicLink()) fail("--prepared-input-set must be a regular file");
  const authorityRoot = realpathSync(coreRoot);
  const realPath = realpathSync(resolved);
  if (realPath !== authorityRoot && !realPath.startsWith(`${authorityRoot}${path.sep}`)) fail("--prepared-input-set must remain under the core authority root");
  return realPath;
}

function ensureCoreFile(value, label) {
  const resolved = corePath(value, label);
  if (!existsSync(resolved) || !lstatSync(resolved).isFile() || lstatSync(resolved).isSymbolicLink()) fail(`${label} must be a regular file`);
  const authorityRoot = realpathSync(coreRoot);
  const realPath = realpathSync(resolved);
  if (realPath !== authorityRoot && !realPath.startsWith(`${authorityRoot}${path.sep}`)) fail(`${label} must remain under the core authority root`);
  return realPath;
}

function ensureCoreDirectory(value, label) {
  const resolved = corePath(value, label);
  if (!existsSync(resolved) || !lstatSync(resolved).isDirectory() || lstatSync(resolved).isSymbolicLink()) fail(`${label} must be a regular directory`);
  const authorityRoot = realpathSync(coreRoot);
  const realPath = realpathSync(resolved);
  if (realPath !== authorityRoot && !realPath.startsWith(`${authorityRoot}${path.sep}`)) fail(`${label} must remain under the core authority root`);
  return realPath;
}

function authorityRelative(file) {
  const relative = path.relative(coreRoot, file);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) fail(`path escapes core authority: ${file}`);
  return relative.split(path.sep).join("/");
}

function walkFiles(root) {
  const files = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const file = path.join(root, entry.name);
    if (entry.isDirectory()) files.push(...walkFiles(file));
    else if (entry.isFile()) files.push(file);
    else if (entry.isSymbolicLink()) fail(`prepared app contains unsupported symlink: ${file}`);
  }
  return files;
}

function inputSet(manifestPath, artifacts = {}, extraFiles = []) {
  const files = [manifestPath, path.join(coreRoot, "shells/tools/capture-native-fixture-batch.mjs")];
  for (const artifact of Object.values(artifacts)) {
    if (artifact?.app && existsSync(artifact.app)) files.push(...walkFiles(artifact.app));
    if (artifact?.stamp && existsSync(artifact.stamp)) files.push(artifact.stamp);
  }
  for (const file of extraFiles) if (existsSync(file)) files.push(file);
  const uniqueFiles = [...new Set(files)];
  const entries = uniqueFiles.map((file) => {
    const stat = statSync(file);
    return {
      key: `core:${authorityRelative(file)}`,
      sha256: hashFile(file),
      size: stat.size,
      mode: stat.mode & 0o777,
    };
  }).sort((left, right) => left.key < right.key ? -1 : left.key > right.key ? 1 : 0);
  const tree = sha256(canonical(entries));
  return { id: `input-v1-${tree}`, entries, tree_sha256: tree };
}

function shellQuote(value) {
  return `'${String(value).replaceAll("'", "'\\''")}'`;
}

function parseQuery(raw, coordinate) {
  if (typeof raw !== "string" || raw.length === 0 || raw.length > 1024 || raw.includes("#")) fail(`${coordinate.run_id}: surface_query is empty, too long, or has a fragment`);
  const values = new Map();
  for (const pair of raw.split("&")) {
    const index = pair.indexOf("=");
    if (index <= 0) fail(`${coordinate.run_id}: surface_query has an empty or valueless pair`);
    let key;
    let value;
    try {
      key = decodeURIComponent(pair.slice(0, index).replaceAll("+", "%20"));
      value = decodeURIComponent(pair.slice(index + 1).replaceAll("+", "%20"));
    } catch {
      fail(`${coordinate.run_id}: surface_query has malformed percent encoding`);
    }
    if (!key || !value || values.has(key)) fail(`${coordinate.run_id}: surface_query has an empty or duplicate key`);
    values.set(key, value);
  }
  const expected = ["polish", "qa", "state", "platform", "theme", "width", "accessibility", "locale"];
  if (values.size !== expected.length || expected.some((key) => !values.has(key))) fail(`${coordinate.run_id}: surface_query keys do not match the capture contract`);
  const expectedValues = {
    polish: "1",
    qa: coordinate.domain === "memories" ? "memories-platform" : coordinate.domain,
    state: coordinate.state,
    platform: coordinate.shell === "macos" ? "desktop" : "mobile",
    theme: coordinate.theme,
    width: coordinate.width,
    accessibility: coordinate.accessibility,
  };
  for (const [key, expectedValue] of Object.entries(expectedValues)) {
    if (values.get(key) !== expectedValue) fail(`${coordinate.run_id}: surface_query ${key} does not match coordinate`);
  }
  if (!safeLocale.test(values.get("locale"))) fail(`${coordinate.run_id}: locale is unsafe`);
  return Object.fromEntries(values);
}

function validateDevice(coordinate) {
  if (!coordinate.device || typeof coordinate.device !== "object") fail(`${coordinate.run_id}: device binding is required`);
  const { udid, model, orientation } = coordinate.device;
  if (typeof udid !== "string" || udid.length < 3 || udid.length > 120 || !/^[A-Za-z0-9._:-]+$/.test(udid)) fail(`${coordinate.run_id}: device.udid is unsafe`);
  if (typeof model !== "string" || model.length < 2 || model.length > 120) fail(`${coordinate.run_id}: device.model is required`);
  if (!validOrientations.has(orientation)) fail(`${coordinate.run_id}: device.orientation is invalid`);
  if (orientation !== widthPolicy[coordinate.shell][coordinate.width].orientation) fail(`${coordinate.run_id}: orientation does not match ${coordinate.shell}/${coordinate.width} policy`);
}

function validateCoordinate(coordinate, root, index) {
  if (!coordinate || typeof coordinate !== "object") fail(`coordinate ${index} is not an object`);
  if (coordinate.schema !== "omi.polish.matrix-coordinate/v1") fail(`${coordinate.run_id ?? `coordinate-${index}`}: schema must be omi.polish.matrix-coordinate/v1`);
  if (coordinate.kind !== "screenshot") fail(`${coordinate.run_id ?? `coordinate-${index}`}: only screenshot coordinates are supported by this batch`);
  for (const [name, values] of [["domain", validDomains], ["shell", validShells], ["state", validStates], ["theme", validThemes], ["width", validWidths], ["accessibility", validAccessibilities]]) {
    if (!values.has(coordinate[name])) fail(`${coordinate.run_id ?? `coordinate-${index}`}: unknown ${name}`);
  }
  if (!safeRunId.test(coordinate.run_id) || ["anonymous", "overflow"].includes(coordinate.run_id) || coordinate.run_id.startsWith("__") || coordinate.run_id.includes("::")) fail(`coordinate ${index}: run_id is unsafe`);
  if (coordinate.capture_class !== "native_fixture") fail(`${coordinate.run_id}: capture_class must be native_fixture`);
  if (coordinate.source_tier !== "native_shell") fail(`${coordinate.run_id}: source_tier must be native_shell`);
  if (!coordinate.source_shas || Object.keys(coordinate.source_shas).sort().join(",") !== "core,platform" || !fullSha.test(coordinate.source_shas.core) || !fullSha.test(coordinate.source_shas.platform)) fail(`${coordinate.run_id}: source_shas must contain only full core/platform SHAs`);
  const policy = widthPolicy[coordinate.shell][coordinate.width];
  if (!coordinate.viewport || coordinate.viewport.width !== policy.width || coordinate.viewport.height !== policy.height || coordinate.viewport.scale !== policy.scale) fail(`${coordinate.run_id}: viewport must exactly match ${coordinate.shell}/${coordinate.width} policy`);
  validateDevice(coordinate);
  const query = parseQuery(coordinate.surface_query, coordinate);
  if (root.source_shas.core !== coordinate.source_shas.core || root.source_shas.platform !== coordinate.source_shas.platform) fail(`${coordinate.run_id}: coordinate source SHAs differ from manifest source SHAs`);
  return { ...coordinate, query };
}

function loadManifest(file) {
  if (!file || !path.isAbsolute(file)) fail("--manifest must be an absolute path");
  let manifest;
  try { manifest = JSON.parse(readFileSync(file, "utf8")); } catch (error) { fail(`manifest cannot be read: ${error.message}`); }
  if (manifest.schema !== "omi.polish.matrix-manifest/v1") fail("manifest schema must be omi.polish.matrix-manifest/v1");
  if (manifest.capture_class !== "native_fixture" || manifest.source_tier !== "native_shell") fail("manifest must be native_fixture/native_shell");
  if (!manifest.source_shas || Object.keys(manifest.source_shas).sort().join(",") !== "core,platform" || !fullSha.test(manifest.source_shas.core) || !fullSha.test(manifest.source_shas.platform)) fail("manifest source SHAs must contain only full core/platform values");
  if (!Array.isArray(manifest.coordinates) || manifest.coordinates.length === 0 || manifest.coordinates.length > maxCoordinates) fail(`manifest coordinates must contain 1..${maxCoordinates} entries`);
  if (manifest.coordinate_count !== manifest.coordinates.length) fail("manifest coordinate_count does not match coordinates");
  const seen = new Set();
  const coordinates = manifest.coordinates.map((coordinate, index) => {
    const validated = validateCoordinate(coordinate, manifest, index);
    if (seen.has(validated.run_id)) fail(`duplicate run_id ${validated.run_id}`);
    seen.add(validated.run_id);
    return validated;
  });
  return { ...manifest, coordinates };
}

function allowedEnvironment(outRoot, shell) {
  const keys = ["PATH", "TMPDIR", "LANG", "LC_ALL", "DEVELOPER_DIR", "SDKROOT", "NODE_BIN", "FLUTTER_BIN", "OMI_SURFACES_DIST"];
  const env = Object.fromEntries(keys.filter((key) => process.env[key]).map((key) => [key, process.env[key]]));
  const scratchHome = path.join(outRoot, "scratch-home", shell);
  mkdirSync(scratchHome, { recursive: true });
  env.HOME = scratchHome;
  env.PUB_CACHE = path.join(scratchHome, ".pub-cache");
  env.XDG_CACHE_HOME = path.join(scratchHome, ".cache");
  env.OMI_SURFACE_PORT = "5290";
  return env;
}

function cleanupEnvironment(env) {
  const home = env?.HOME;
  if (typeof home !== "string") return;
  const scratchRoot = path.dirname(home);
  if (path.basename(scratchRoot) !== "scratch-home") return;
  if (existsSync(scratchRoot) && !lstatSync(scratchRoot).isSymbolicLink()) {
    rmSync(scratchRoot, { recursive: true, force: true });
  }
}

function commandSpec(command, args, cwd, env, timeoutSeconds) {
  return { command, args, cwd, env, timeoutSeconds };
}

function runCommand(spec, label) {
  const result = spawnSync(spec.command, spec.args, {
    cwd: spec.cwd,
    env: spec.env,
    encoding: "utf8",
    timeout: spec.timeoutSeconds * 1000,
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.error?.code === "ETIMEDOUT" || result.signal === "SIGTERM") fail(`${label} timed out after ${spec.timeoutSeconds}s`);
  if (result.status !== 0) fail(`${label} failed (exit ${result.status ?? "signal"}): ${(result.stderr || result.stdout || "").trim().slice(-600)}`);
  return result;
}

function writeAtomic(file, value) {
  const temporary = `${file}.tmp-${process.pid}`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  renameSync(temporary, file);
}

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

function decodeRgbaImage(file) {
  const bytes = readFileSync(file);
  const magic = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  if (bytes.length < 24 || !bytes.subarray(0, 8).equals(magic) || bytes.toString("ascii", 12, 16) !== "IHDR") fail(`capture ${file} is not a valid PNG`);
  const width = bytes.readUInt32BE(16);
  const height = bytes.readUInt32BE(20);
  if (bytes[24] !== 8 || bytes[25] !== 6 || bytes[26] !== 0 || bytes[27] !== 0 || bytes[28] !== 0) {
    fail(`capture ${file} must be a non-interlaced 8-bit RGBA PNG`);
  }
  const idat = [];
  for (let offset = 8; offset + 12 <= bytes.length;) {
    const length = bytes.readUInt32BE(offset);
    const end = offset + 12 + length;
    if (end > bytes.length) fail(`capture ${file} has a truncated PNG chunk`);
    if (bytes.toString("ascii", offset + 4, offset + 8) === "IDAT") idat.push(bytes.subarray(offset + 8, offset + 8 + length));
    offset = end;
  }
  if (idat.length === 0) fail(`capture ${file} has no PNG image data`);
  let inflated;
  try { inflated = inflateSync(Buffer.concat(idat), { maxOutputLength: height * (width * 4 + 1) }); }
  catch { fail(`capture ${file} has invalid PNG image data`); }
  const stride = width * 4;
  if (inflated.length !== height * (stride + 1)) fail(`capture ${file} has unexpected PNG image data length`);
  const previous = Buffer.alloc(stride);
  const current = Buffer.alloc(stride);
  const rgba = Buffer.alloc(height * stride);
  let firstPixel = null;
  let varied = false;
  const paeth = (left, above, upperLeft) => {
    const estimate = left + above - upperLeft;
    const leftDistance = Math.abs(estimate - left);
    const aboveDistance = Math.abs(estimate - above);
    const upperLeftDistance = Math.abs(estimate - upperLeft);
    return leftDistance <= aboveDistance && leftDistance <= upperLeftDistance ? left : aboveDistance <= upperLeftDistance ? above : upperLeft;
  };
  for (let row = 0; row < height; row += 1) {
    const inputOffset = row * (stride + 1);
    const filter = inflated[inputOffset];
    if (filter > 4) fail(`capture ${file} has an unsupported PNG filter`);
    for (let column = 0; column < stride; column += 1) {
      const raw = inflated[inputOffset + 1 + column];
      const left = column >= 4 ? current[column - 4] : 0;
      const above = previous[column];
      const upperLeft = column >= 4 ? previous[column - 4] : 0;
      const predictor = filter === 1 ? left
        : filter === 2 ? above
        : filter === 3 ? Math.floor((left + above) / 2)
        : filter === 4 ? paeth(left, above, upperLeft)
        : 0;
      current[column] = (raw + predictor) & 0xff;
    }
    for (let column = 0; column < stride; column += 4) {
      const pixel = `${current[column]},${current[column + 1]},${current[column + 2]},${current[column + 3]}`;
      if (firstPixel === null) firstPixel = pixel;
      else if (pixel !== firstPixel) varied = true;
    }
    current.copy(rgba, row * stride);
    current.copy(previous);
  }
  return { bytes, width, height, rgba, varied };
}

function imageInfo(file) {
  const image = decodeRgbaImage(file);
  if (!image.varied) fail(`capture ${file} is a uniform framebuffer and cannot prove rendered UI`);
  return { bytes: image.bytes.length, width: image.width, height: image.height, sha256: sha256(image.bytes) };
}

function canonicalizeScreenshot(file) {
  const image = decodeRgbaImage(file);
  // CoreSimulator can vary a handful of near-black antialiasing bytes by one
  // value across otherwise identical launches. Collapse only RGB values below
  // 16 to black, retain every other byte plus alpha and geometry exactly, and
  // encode filter-0 rows through Node's deterministic zlib implementation.
  // Visible product pixels remain untouched while the observed compositor
  // fringe becomes replay-stable.
  for (let offset = 0; offset < image.rgba.length; offset += 4) {
    if (image.rgba[offset] < 16) image.rgba[offset] = 0;
    if (image.rgba[offset + 1] < 16) image.rgba[offset + 1] = 0;
    if (image.rgba[offset + 2] < 16) image.rgba[offset + 2] = 0;
  }
  const stride = image.width * 4;
  const rows = Buffer.alloc(image.height * (stride + 1));
  for (let row = 0; row < image.height; row += 1) {
    image.rgba.copy(rows, row * (stride + 1) + 1, row * stride, (row + 1) * stride);
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(image.width, 0);
  header.writeUInt32BE(image.height, 4);
  header[8] = 8;
  header[9] = 6;
  const canonical = Buffer.concat([
    Buffer.from("\x89PNG\r\n\x1a\n", "binary"),
    pngChunk("IHDR", header),
    pngChunk("IDAT", deflateSync(rows, { level: 9 })),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
  const temporary = `${file}.canonical-${process.pid}`;
  writeFileSync(temporary, canonical, { mode: 0o600 });
  renameSync(temporary, file);
}

export function canonicalizeScreenshotForTest(file) {
  canonicalizeScreenshot(file);
}

function validateImage(file, coordinate) {
  const info = imageInfo(file);
  const expected = coordinate.viewport;
  const allowed = new Set([`${expected.width}x${expected.height}`, `${expected.width * expected.scale}x${expected.height * expected.scale}`]);
  if (!allowed.has(`${info.width}x${info.height}`)) fail(`${coordinate.run_id}: PNG dimensions ${info.width}x${info.height} do not match ${expected.width}x${expected.height} @${expected.scale}`);
  return info;
}

function buildMac(manifest, outRoot, batchId) {
  const buildDir = path.join(outRoot, "build", "macos");
  mkdirSync(buildDir, { recursive: true });
  const env = allowedEnvironment(outRoot, "macos");
  env.OMI_BUILD_DIR = buildDir;
  env.OMI_APP_NAME = "omi-on-polish-batch";
  const dist = process.env.OMI_SURFACES_DIST || path.join(coreRoot, "packages/surfaces/dist");
  if (!existsSync(path.join(dist, "index.html"))) fail(`surfaces dist missing at ${dist}; build @omi-core/surfaces first`);
  env.OMI_SURFACES_DIST = dist;
  runCommand(commandSpec("/bin/bash", [path.join(coreRoot, "shells/macos/scripts/build-shell.sh")], coreRoot, env, 300), "macOS one-time build");
  const app = path.join(buildDir, "omi-on-polish-batch.app");
  if (!existsSync(path.join(app, "Contents/MacOS/omi-on-polish-batch"))) fail("macOS build did not produce the scratch app");
  return { shell: "macos", buildDir, app, env, batchId, stamp: path.join(app, "Contents/Resources/omi-build-stamp.json") };
}

function buildIos(manifest, outRoot, batchId) {
  const flutter = process.env.FLUTTER_BIN;
  if (!flutter || !path.isAbsolute(flutter)) fail("iOS batch requires absolute FLUTTER_BIN (managed Flutter 3.44.5)");
  const env = allowedEnvironment(outRoot, "ios");
  env.FLUTTER_BIN = flutter;
  const appRoot = path.join(coreRoot, "shells/ios");
  const buildDir = path.join(outRoot, "build", "ios");
  mkdirSync(buildDir, { recursive: true });
  const dist = process.env.OMI_SURFACES_DIST || path.join(coreRoot, "packages/surfaces/dist");
  if (!existsSync(path.join(dist, "index.html"))) fail(`surfaces dist missing at ${dist}; build @omi-core/surfaces first`);
  env.SURFACES_DIST = dist;
  runCommand(commandSpec(process.env.NODE_BIN || "node", [path.join(appRoot, "tools/build-surfaces-bundle.mjs")], appRoot, env, 300), "iOS one-time surfaces bundle");
  const fallbackQuery = manifest.coordinates.find((coordinate) => coordinate.shell === "ios")?.surface_query;
  if (!fallbackQuery) fail("iOS build requested with no iOS coordinates");
  const defines = [
    "--dart-define=SURFACE_MODE=scheme",
    "--dart-define=SCHEME_BUNDLE=surfaces",
    "--dart-define=OMI_CAPTURE_ONLY=true",
    `--dart-define=SURFACE_QUERY=${fallbackQuery}`,
  ];
  const flutterAppRoot = path.join(appRoot, "app");
  const relativeBuildDir = path.relative(flutterAppRoot, buildDir);
  if (!relativeBuildDir || path.isAbsolute(relativeBuildDir)) fail("iOS build directory must be relative to the Flutter app");
  // Flutter 3.44 removed the build subcommand's --build-dir option. Configure
  // it inside the already-isolated scratch HOME, then perform the build. This
  // keeps generated output under the declared core authority without changing
  // the operator's global Flutter configuration.
  try {
    runCommand(commandSpec(flutter, ["config", `--build-dir=${relativeBuildDir}`], flutterAppRoot, env, 30), "iOS scratch build directory");
    runCommand(commandSpec(flutter, ["build", "ios", "--simulator", "--debug", ...defines], flutterAppRoot, env, 600), "iOS one-time build");
    const bundle = path.join(buildDir, "ios/iphonesimulator/Runner.app");
    if (!existsSync(bundle)) fail("iOS build did not produce Runner.app");
    const bundleId = "me.omi.proto.omiWebviewProto";
    const sourceStamp = path.join(appRoot, "app/assets/surfaces/omi-ios-shell-build-stamp.json");
    const stamp = path.join(buildDir, "omi-ios-shell-build-stamp.json");
    if (existsSync(sourceStamp)) copyFileSync(sourceStamp, stamp);
    return { shell: "ios", buildDir, app: bundle, bundleId, env, batchId, stamp, installedDevices: new Set(), frozenDevices: new Set(), appearanceByDevice: new Map(), geometryByDevice: new Map() };
  } finally {
    const ephemeral = path.join(flutterAppRoot, "ios/Flutter/ephemeral");
    if (existsSync(ephemeral) && !lstatSync(ephemeral).isSymbolicLink()) {
      rmSync(ephemeral, { recursive: true, force: true });
    }
  }
}

function artifactDescriptor(artifact) {
  return {
    shell: artifact.shell,
    app: `core:${authorityRelative(artifact.app)}`,
    build_dir: `core:${authorityRelative(artifact.buildDir)}`,
    stamp: `core:${authorityRelative(artifact.stamp)}`,
    stamp_sha256: existsSync(artifact.stamp) ? hashFile(artifact.stamp) : null,
    bundle_id: artifact.bundleId || null,
  };
}

function writePreparedInputSet(file, manifestPath, manifest, coordinates, outRoot, shell, artifacts) {
  const descriptor = {
    schema: "omi.polish.native-fixture-prepared/v1",
    source_shas: manifest.source_shas,
    manifest_path: `core:${authorityRelative(manifestPath)}`,
    manifest_sha256: hashFile(manifestPath),
    shell,
    scope: "manifest-shell",
    coordinate_run_ids: coordinates.map((coordinate) => coordinate.run_id),
    artifacts: Object.fromEntries(Object.entries(artifacts).map(([name, artifact]) => [name, artifactDescriptor(artifact)])),
    authority: { fixture: true, bridge: "disabled", credentials: false, production_api: false, origins: { macos: "http://127.0.0.1:5290", ios: "omi-ui://local" } },
  };
  writeAtomic(file, descriptor);
  // The descriptor is an immutable input to capture, but deliberately does
  // not contain its own hash (which would make a canonical input-set cycle).
  return descriptor;
}

function resolvePreparedArtifact(descriptor, name) {
  const item = descriptor.artifacts?.[name];
  if (!item || typeof item.app !== "string" || !item.app.startsWith("core:")) fail(`prepared input set is missing ${name} app`);
  if (name === "ios" && item.bundle_id !== "me.omi.proto.omiWebviewProto") fail("prepared iOS bundle id is not the capture shell");
  if (name === "macos" && item.bundle_id !== null) fail("prepared macOS bundle id must be null");
  const app = ensureCoreDirectory(item.app.slice("core:".length), `${name} app`);
  const buildDir = ensureCoreDirectory(String(item.build_dir || "").replace(/^core:/, ""), `${name} build_dir`);
  const stamp = ensureCoreFile(String(item.stamp || "").replace(/^core:/, ""), `${name} stamp`);
  if (!existsSync(app) || !lstatSync(app).isDirectory()) fail(`prepared ${name} app is unavailable`);
  if (!existsSync(stamp) || !lstatSync(stamp).isFile()) fail(`prepared ${name} build stamp is unavailable`);
  if (item.stamp_sha256 && hashFile(stamp) !== item.stamp_sha256) fail(`prepared ${name} build stamp changed`);
  if (!existsSync(buildDir) || !lstatSync(buildDir).isDirectory()) fail(`prepared ${name} build directory is unavailable`);
  const artifact = { shell: name, app, buildDir, stamp, bundleId: item.bundle_id || null, env: null, installedDevices: new Set(), frozenDevices: new Set(), appearanceByDevice: new Map(), geometryByDevice: new Map() };
  artifact.env = allowedEnvironment(path.dirname(path.dirname(buildDir)), name);
  return artifact;
}

function loadPreparedInputSet(file, manifestPath, manifest, shell) {
  let descriptor;
  try { descriptor = JSON.parse(readFileSync(file, "utf8")); } catch (error) { fail(`prepared input set cannot be read: ${error.message}`); }
  if (descriptor.schema !== "omi.polish.native-fixture-prepared/v1") fail("prepared input set schema is invalid");
  if (descriptor.source_shas?.core !== manifest.source_shas.core || descriptor.source_shas?.platform !== manifest.source_shas.platform) fail("prepared input set source SHAs are stale");
  if (descriptor.manifest_path !== `core:${authorityRelative(manifestPath)}` || descriptor.manifest_sha256 !== hashFile(manifestPath)) fail("prepared input set manifest binding is stale");
  if (descriptor.shell !== shell && descriptor.shell !== "both") fail("prepared input set shell does not cover capture shell");
  if (descriptor.scope !== "manifest-shell") fail("prepared input set scope is invalid");
  const expectedRunIds = manifest.coordinates
    .filter((coordinate) => shell === "both" || coordinate.shell === shell)
    .map((coordinate) => coordinate.run_id);
  if (!Array.isArray(descriptor.coordinate_run_ids) || canonical(descriptor.coordinate_run_ids) !== canonical(expectedRunIds)) fail("prepared input set coordinate scope is stale");
  const artifacts = {};
  if (shell === "both" || shell === "macos") artifacts.macos = resolvePreparedArtifact(descriptor, "macos");
  if (shell === "both" || shell === "ios") artifacts.ios = resolvePreparedArtifact(descriptor, "ios");
  const preparedBaseInput = inputSet(manifestPath, artifacts);
  if (!descriptor.input_set || canonical(descriptor.input_set) !== canonical(preparedBaseInput)) fail("prepared input set file list/hash is stale");
  return { descriptor, artifacts, input: inputSet(manifestPath, artifacts, [file]) };
}

function verifyIosDevice(coordinate, env) {
  const result = runCommand(commandSpec("xcrun", ["simctl", "list", "devices", "-j"], coreRoot, env, 30), "iOS device inventory");
  let document;
  try { document = JSON.parse(result.stdout); } catch { fail("iOS device inventory was not JSON"); }
  const devices = Object.values(document.devices || {}).flat();
  const device = devices.find((candidate) => candidate.udid === coordinate.device.udid);
  if (!device) fail(`${coordinate.run_id}: simulator ${coordinate.device.udid} is unavailable`);
  if (device.state !== "Booted") fail(`${coordinate.run_id}: simulator ${coordinate.device.udid} is not Booted`);
  if (device.name !== coordinate.device.model && device.deviceTypeIdentifier !== coordinate.device.model) fail(`${coordinate.run_id}: simulator model does not match manifest (${device.name}/${device.deviceTypeIdentifier})`);
  return device;
}

function freezeIosStatusBar(device, env) {
  runCommand(commandSpec("xcrun", ["simctl", "status_bar", device, "override", "--time", "9:41", "--dataNetwork", "5g", "--wifiMode", "active", "--wifiBars", "3", "--cellularMode", "active", "--cellularBars", "4", "--operatorName", "Omi", "--batteryLevel", "100", "--batteryState", "charged"], coreRoot, env, 30), `${device}: freeze simulator status bar`);
}

function clearIosStatusBar(device, env) {
  const result = spawnSync("xcrun", ["simctl", "status_bar", device, "clear"], { cwd: coreRoot, env, encoding: "utf8", stdio: "ignore", timeout: 30_000 });
  if (result.error?.code === "ETIMEDOUT") fail(`${device}: status bar clear timed out`);
}

function queryIosAppearance(device, env) {
  const result = spawnSync("xcrun", ["simctl", "ui", device, "appearance"], { cwd: coreRoot, env, encoding: "utf8", timeout: 30_000 });
  if (result.status !== 0) return null;
  const value = result.stdout.trim();
  return ["light", "dark"].includes(value) ? value : null;
}

function setIosAppearance(device, appearance, env) {
  runCommand(commandSpec("xcrun", ["simctl", "ui", device, "appearance", appearance], coreRoot, env, 30), `${device}: set ${appearance} appearance`);
}

function queryIosGeometry(device, env) {
  const result = spawnSync("xcrun", ["simctl", "io", device, "screenConfig", "geometry"], { cwd: coreRoot, env, encoding: "utf8", timeout: 30_000 });
  if (result.status !== 0) return null;
  const match = `${result.stdout}\n${result.stderr}`.match(/(\d+x\d+@\d+(?:\.\d+)?)/);
  return match ? match[1] : null;
}

function setIosGeometry(device, viewport, env) {
  // simctl takes framebuffer pixels, while the manifest records the logical
  // viewport plus scale. Passing logical points makes every real managed
  // simulator reject an otherwise correct binding.
  const pixelWidth = viewport.width * viewport.scale;
  const pixelHeight = viewport.height * viewport.scale;
  runCommand(commandSpec("xcrun", ["simctl", "io", device, "screenConfig", "geometry", `${pixelWidth}x${pixelHeight}@${viewport.scale}`], coreRoot, env, 30), `${device}: set screenshot geometry`);
}

function restoreIosDevice(device, artifact) {
  const appearance = artifact.appearanceByDevice.get(device);
  if (appearance) {
    const result = spawnSync("xcrun", ["simctl", "ui", device, "appearance", appearance], { cwd: coreRoot, env: artifact.env, encoding: "utf8", timeout: 30_000, stdio: "ignore" });
    if (result.error?.code === "ETIMEDOUT") console.error(`${device}: appearance restore timed out`);
  }
  const geometry = artifact.geometryByDevice.get(device);
  if (geometry) {
    const result = spawnSync("xcrun", ["simctl", "io", device, "screenConfig", "geometry", geometry], { cwd: coreRoot, env: artifact.env, encoding: "utf8", timeout: 30_000, stdio: "ignore" });
    if (result.error?.code === "ETIMEDOUT") console.error(`${device}: geometry restore timed out`);
  }
}

function terminateIosApp(device, bundleId, env, label) {
  const result = spawnSync("xcrun", ["simctl", "terminate", device, bundleId], {
    cwd: coreRoot,
    env,
    encoding: "utf8",
    timeout: 30_000,
  });
  if (result.error?.code === "ETIMEDOUT") fail(`${label}: simulator app termination timed out`);
  const output = `${result.stdout || ""}\n${result.stderr || ""}`;
  // A clean capture starts with no app process. simctl reports that expected
  // state as POSIX ESRCH instead of success; accept only its exact bounded
  // diagnostic and reject every other nonzero termination result.
  if (result.status !== 0 && !output.includes("found nothing to terminate")) {
    fail(`${label}: simulator app termination failed (exit ${result.status ?? "signal"})`);
  }
}

function iosAppDataContainer(device, bundleId, env, runId) {
  const result = runCommand(
    commandSpec("xcrun", ["simctl", "get_app_container", device, bundleId, "data"], coreRoot, env, 30),
    `${runId}: resolve capture app data container`,
  );
  const container = result.stdout.trim();
  const expectedContainer = new RegExp(
    `^/Users/[^/]+/Library/Developer/CoreSimulator/Devices/${device.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/data/Containers/Data/Application/[A-F0-9-]+$`,
  );
  if (!path.isAbsolute(container) || !expectedContainer.test(container)) {
    fail(`${runId}: simulator returned an unbound app data container`);
  }
  return container;
}

function readIosReadiness(device, markerPath, env) {
  const result = spawnSync("xcrun", ["simctl", "spawn", device, "/bin/cat", markerPath], {
    cwd: coreRoot,
    env,
    encoding: "utf8",
    timeout: 30_000,
  });
  if (result.error?.code === "ETIMEDOUT") fail(`${device}: capture readiness read timed out`);
  if (result.status !== 0) return null;
  try { return JSON.parse(result.stdout); } catch { return null; }
}

function waitForIosReadiness(coordinate, artifact, markerPath, nonce, waitSeconds) {
  const deadline = Date.now() + waitSeconds * 1000;
  while (Date.now() <= deadline) {
    const marker = readIosReadiness(coordinate.device.udid, markerPath, artifact.env);
    if (marker &&
        Object.keys(marker).sort().join(",") === "domain,fixture,nonce,polish_state,route,run_id,state" &&
        marker.nonce === nonce &&
        marker.run_id === coordinate.run_id &&
        marker.domain === coordinate.domain &&
        marker.polish_state === coordinate.state &&
        marker.route === coordinate.domain &&
        marker.fixture === fixturePolicy[coordinate.domain]?.[coordinate.state] &&
        typeof marker.state === "string" &&
        /^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/.test(marker.state)) {
      return;
    }
    const remaining = deadline - Date.now();
    if (remaining <= 0) break;
    spawnSync("sleep", [String(Math.min(0.25, remaining / 1000))], {
      cwd: coreRoot,
      env: artifact.env,
      encoding: "utf8",
      timeout: 2_000,
    });
  }
  fail(`${coordinate.run_id}: capture app did not publish the run-bound readiness record`);
}

function captureMac(coordinate, artifact, output, timeoutSeconds) {
  const env = { ...artifact.env };
  env.OMI_SURFACE_QUERY = coordinate.surface_query;
  env.OMI_RUN_CLIENT_ID = coordinate.run_id;
  env.OMI_SNAPSHOT_PATH = output;
  env.OMI_PROBE_EXIT = "1";
  env.OMI_NATIVE_VIEWPORT_WIDTH = String(coordinate.viewport.width);
  env.OMI_NATIVE_VIEWPORT_HEIGHT = String(coordinate.viewport.height);
  env.OMI_APP_NAME = "omi-on-polish-batch";
  env.OMI_BUILD_DIR = artifact.buildDir;
  const result = spawnSync(path.join(artifact.app, "Contents/MacOS/omi-on-polish-batch"), [], {
    cwd: coreRoot,
    env,
    encoding: "utf8",
    timeout: timeoutSeconds * 1000,
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.error?.code === "ETIMEDOUT" || result.signal === "SIGTERM") fail(`${coordinate.run_id}: macOS capture timed out`);
  if (result.status !== 0) fail(`${coordinate.run_id}: macOS capture failed (exit ${result.status ?? "signal"})`);
}

function captureIos(coordinate, artifact, output, waitSeconds, timeoutSeconds) {
  verifyIosDevice(coordinate, artifact.env);
  if (!artifact.appearanceByDevice.has(coordinate.device.udid)) artifact.appearanceByDevice.set(coordinate.device.udid, queryIosAppearance(coordinate.device.udid, artifact.env));
  if (!artifact.geometryByDevice.has(coordinate.device.udid)) artifact.geometryByDevice.set(coordinate.device.udid, queryIosGeometry(coordinate.device.udid, artifact.env));
  setIosAppearance(coordinate.device.udid, coordinate.theme, artifact.env);
  setIosGeometry(coordinate.device.udid, coordinate.viewport, artifact.env);
  terminateIosApp(coordinate.device.udid, artifact.bundleId, artifact.env, `${coordinate.run_id}: terminate prior app`);
  const stdoutPath = `${output}.app.stdout`;
  const stderrPath = `${output}.app.stderr`;
  const readinessNonce = randomBytes(32).toString("hex");
  const markerPath = path.join(
    iosAppDataContainer(coordinate.device.udid, artifact.bundleId, artifact.env, coordinate.run_id),
    "Library",
    "Caches",
    "omi-native-capture-ready.json",
  );
  rmSync(stdoutPath, { force: true });
  rmSync(stderrPath, { force: true });
  let launched = false;
  try {
    launched = true;
    runCommand(commandSpec("xcrun", ["simctl", "launch", `--stdout=${stdoutPath}`, `--stderr=${stderrPath}`, coordinate.device.udid, artifact.bundleId, `--omi-capture-query=${coordinate.surface_query}`, `--omi-capture-run-id=${coordinate.run_id}`, `--omi-capture-nonce=${readinessNonce}`], coreRoot, artifact.env, 30), `${coordinate.run_id}: launch capture app`);
    waitForIosReadiness(coordinate, artifact, markerPath, readinessNonce, waitSeconds);
    // CoreSimulator can report DOM readiness one compositor frame before its
    // text/glyph surfaces settle. Capture and discard that first native frame
    // so both the retained image and a later strict replay begin at the same
    // compositor phase. This remains a real device screenshot; it is not a
    // browser render or a substituted fixture artifact.
    const warmupOutput = `${output}.warmup.png`;
    rmSync(warmupOutput, { force: true });
    runCommand(commandSpec("xcrun", ["simctl", "io", coordinate.device.udid, "screenshot", warmupOutput], coreRoot, artifact.env, timeoutSeconds), `${coordinate.run_id}: settle simulator compositor`);
    rmSync(warmupOutput, { force: true });
    runCommand(commandSpec("xcrun", ["simctl", "io", coordinate.device.udid, "screenshot", output], coreRoot, artifact.env, timeoutSeconds), `${coordinate.run_id}: simulator screenshot`);
  } finally {
    if (launched) terminateIosApp(coordinate.device.udid, artifact.bundleId, artifact.env, `${coordinate.run_id}: cleanup app`);
    rmSync(stdoutPath, { force: true });
    rmSync(stderrPath, { force: true });
  }
}

function prepareIosArtifact(artifact, coordinates) {
  for (const coordinate of coordinates.filter((entry) => entry.shell === "ios")) {
    if (!artifact.installedDevices.has(coordinate.device.udid)) {
      verifyIosDevice(coordinate, artifact.env);
      runCommand(commandSpec("xcrun", ["simctl", "install", coordinate.device.udid, artifact.app], coreRoot, artifact.env, 120), `${coordinate.run_id}: install capture app once for device`);
      artifact.installedDevices.add(coordinate.device.udid);
    }
    if (!artifact.frozenDevices.has(coordinate.device.udid)) {
      freezeIosStatusBar(coordinate.device.udid, artifact.env);
      artifact.frozenDevices.add(coordinate.device.udid);
    }
  }
}

function loadJson(file, label) {
  try { return JSON.parse(readFileSync(file, "utf8")); }
  catch (error) { fail(`${label} cannot be read: ${error.message}`); }
}

function assembleReceipt(resultPath, outRoot, manifestPath, manifest, args) {
  const result = loadJson(resultPath, "batch result");
  if (result.schema !== "omi.polish.native-fixture-batch-result/v1") fail("batch result schema is invalid");
  if (result.batch_id !== undefined || result.generated_at !== undefined) fail("batch result must not contain batch_id or timestamps");
  if (result.source_shas?.core !== manifest.source_shas.core || result.source_shas?.platform !== manifest.source_shas.platform) fail("batch result source SHAs are stale");
  if (result.manifest_path !== `core:${authorityRelative(manifestPath)}` || result.manifest_sha256 !== hashFile(manifestPath)) fail("batch result manifest binding is stale");
  if (typeof result.command !== "string" || !Array.isArray(result.argv) || !result.input_set || !result.members || typeof result.members !== "object") fail("batch result is missing command/input/member bindings");
  const members = result.members;
  const memberIds = Object.keys(members).sort();
  if (memberIds.length === 0 || memberIds.some((id, index) => id !== `m${String(index).padStart(4, "0")}`)) fail("batch result members are not canonical");
  for (const memberId of memberIds) {
    const member = members[memberId];
    if (!member || !Array.isArray(member.coordinate) || member.coordinate.length !== 7 || !member.run_id || !member.evidence || !member.sidecar) fail(`batch result member ${memberId} is malformed`);
    for (const artifact of [member.evidence, member.sidecar]) {
      if (artifact.root !== "core" || typeof artifact.path !== "string" || !hex64.test(artifact.sha256)) fail(`batch result member ${memberId} has malformed artifact binding`);
      const file = ensureCoreFile(artifact.path, `${memberId} artifact`);
      if (hashFile(file) !== artifact.sha256) fail(`batch result member ${memberId} artifact hash changed`);
    }
  }
  const expectedBatchId = canonicalBatchId(result.input_set.id, result.command, members);
  const resultSha = hashFile(resultPath);
  const timeoutSeconds = Number(result.timeout_seconds);
  if (!Number.isInteger(timeoutSeconds) || timeoutSeconds < 30 || timeoutSeconds > 300) fail("batch result timeout is invalid");
  const startedAt = args.started_at;
  const finishedAt = args.finished_at;
  if (typeof startedAt !== "string" || typeof finishedAt !== "string" || Number.isNaN(Date.parse(startedAt)) || Number.isNaN(Date.parse(finishedAt)) || Date.parse(finishedAt) < Date.parse(startedAt)) fail("--started-at/--finished-at must be ordered ISO timestamps");
  if ((Date.parse(finishedAt) - Date.parse(startedAt)) / 1000 > timeoutSeconds) fail("assembled capture duration exceeds timeout");
  if (args.stdout_file && hashFile(ensureCoreFile(args.stdout_file, "--stdout-file")) !== result.stdout_sha256) fail("captured stdout hash does not match batch result");
  if (args.stderr_file && hashFile(ensureCoreFile(args.stderr_file, "--stderr-file")) !== result.stderr_sha256) fail("captured stderr hash does not match batch result");
  const resultArtifact = { root: "core", path: authorityRelative(resultPath), sha256: resultSha };
  const artifactHashes = { [`${resultArtifact.root}:${resultArtifact.path}`]: resultSha };
  const artifactBeforeHashes = { [`${resultArtifact.root}:${resultArtifact.path}`]: null };
  const artifactCreated = { [`${resultArtifact.root}:${resultArtifact.path}`]: true };
  for (const member of Object.values(members)) {
    for (const artifact of [member.evidence, member.sidecar]) {
      const key = `${artifact.root}:${artifact.path}`;
      artifactHashes[key] = artifact.sha256;
      artifactBeforeHashes[key] = null;
      artifactCreated[key] = true;
    }
  }
  const commandReceipt = {
    argv: result.argv,
    cwd: ".", cwd_root: "core", exit_code: 0, timeout_seconds: timeoutSeconds, started_at: startedAt, finished_at: finishedAt, run_id: expectedBatchId, source_shas: result.source_shas,
    stdout_sha256: result.stdout_sha256, stderr_sha256: result.stderr_sha256, artifact_hashes: artifactHashes, artifact_before_hashes: artifactBeforeHashes, artifact_created: artifactCreated,
    capture_class: "native_fixture", source_tier: "native_shell", input_set: result.input_set, batch_id: expectedBatchId, batch_members: members,
  };
  const coverage = Object.values(members).map((member, index) => {
    const [kind, domain, shell, state, theme, width, accessibility] = member.coordinate;
    return {
      kind, domain, shell, state, theme, width, accessibility, capture_class: "native_fixture", source_tier: "native_shell", root: member.evidence.root, path: member.evidence.path, sha256: member.evidence.sha256,
      command: result.command, command_ran: true, command_receipt: commandReceipt, run_id: member.run_id, sidecar: member.sidecar.path, source_shas: result.source_shas, input_set_id: result.input_set.id, batch_id: expectedBatchId, batch_member: `m${String(index).padStart(4, "0")}`,
    };
  });
  const receipt = {
    schema: "omi.polish.native-fixture-batch/v1", batch_id: expectedBatchId, command: result.command, command_receipt: commandReceipt, input_set: result.input_set, batch_members: members, coverage,
    manifest_path: result.manifest_path, manifest_sha256: result.manifest_sha256, source_shas: result.source_shas, coordinate_count: coverage.length,
    result_artifact: resultArtifact,
    authority: result.authority,
  };
  const receiptPath = path.join(outRoot, `${expectedBatchId}.receipt.json`);
  writeAtomic(receiptPath, receipt);
  process.stdout.write(`NATIVE_FIXTURE_RECEIPT: ${expectedBatchId} file=${authorityRelative(receiptPath)}\n`);
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) { console.log(usage()); return; }
  if (!args.manifest || !args.out_root) fail(`${usage()}\n--manifest and --out-root are required`);
  const manifestPath = ensureManifestPath(args.manifest);
  const manifest = loadManifest(manifestPath);
  const currentSha = currentCoreSha(manifest.source_shas.core);
  if (manifest.source_shas.core !== currentSha) fail(`manifest core SHA ${manifest.source_shas.core} does not match current core HEAD ${currentSha}`);
  const outRoot = ensureOutputRoot(args.out_root);
  if (args.assemble_receipt) {
    if (args.prepare || args.dry_run || args.prepared_input_set) fail("--assemble-receipt cannot be combined with capture/build flags");
    if (!args.result_path || !args.started_at || !args.finished_at) fail("--assemble-receipt requires --result-path, --started-at, and --finished-at");
    assembleReceipt(ensureCoreFile(args.result_path, "--result-path"), outRoot, manifestPath, manifest, args);
    return;
  }
  const shell = args.shell || "both";
  if (!["both", "macos", "ios"].includes(shell)) fail("--shell must be macos, ios, or both");
  const offset = args.offset === undefined ? 0 : Number(args.offset);
  const shellCoordinates = manifest.coordinates.filter((coordinate) => shell === "both" || coordinate.shell === shell);
  const limit = args.limit === undefined ? shellCoordinates.length - offset : Number(args.limit);
  if (!Number.isInteger(offset) || offset < 0 || offset >= shellCoordinates.length) fail("--offset must select a coordinate in the manifest");
  if (!Number.isInteger(limit) || limit < 1 || limit > maxBatchCoordinates || offset + limit > shellCoordinates.length) fail(`--limit must be 1..${maxBatchCoordinates} and offset+limit must remain within the selected manifest coordinates`);
  const coordinates = shellCoordinates.slice(offset, offset + limit);
  if (coordinates.length === 0) fail(`manifest has no ${shell} screenshot coordinates`);
  const manifestHash = hashFile(manifestPath);
  if (args.prepare && args.prepared_input_set) fail("--prepare and --prepared-input-set are mutually exclusive");
  if (!args.prepare && !args.dry_run && !args.prepared_input_set) fail("capture requires --prepared-input-set; use --prepare to build a mode-bound input set first");
  const preparedPath = args.prepared_input_set ? ensurePreparedPath(args.prepared_input_set) : path.join(outRoot, "prepared-input-set.json");
  let input = inputSet(manifestPath, {}, args.prepare ? [] : [preparedPath]);
  const commandParts = ["node", "shells/tools/capture-native-fixture-batch.mjs", "--manifest", authorityRelative(manifestPath), "--out-root", authorityRelative(outRoot), "--shell", shell, "--offset", String(offset), "--limit", String(limit)];
  if (!args.prepare && !args.dry_run) commandParts.push("--prepared-input-set", authorityRelative(preparedPath));
  if (args.prepare) commandParts.push("--prepare");
  if (args.replay_proof) commandParts.push("--replay-proof");
  const timeoutSeconds = args.timeout_seconds === undefined ? 300 : Number(args.timeout_seconds);
  const waitSeconds = args.wait_seconds === undefined ? 5 : Number(args.wait_seconds);
  if (!Number.isInteger(timeoutSeconds) || timeoutSeconds < 30 || timeoutSeconds > 300) fail("--timeout-seconds must be 30..300");
  if (!Number.isInteger(waitSeconds) || waitSeconds < 1 || waitSeconds > 30) fail("--wait-seconds must be 1..30");
  const estimatedSeconds = coordinates.reduce((total, coordinate) => total + (coordinate.shell === "ios" ? waitSeconds + 20 : 20), 0) + 15;
  if (!args.prepare && !args.dry_run && estimatedSeconds > timeoutSeconds) fail(`capture range is estimated at ${estimatedSeconds}s, above timeout ${timeoutSeconds}s; use a smaller --offset/--limit range`);
  commandParts.push("--timeout-seconds", String(timeoutSeconds), "--wait-seconds", String(waitSeconds));
  const command = commandParts.map(shellQuote).join(" ");
  const previewMembers = Object.fromEntries(coordinates.map((coordinate, index) => [`m${String(index).padStart(4, "0")}`, { coordinate: [coordinate.kind, coordinate.domain, coordinate.shell, coordinate.state, coordinate.theme, coordinate.width, coordinate.accessibility], run_id: coordinate.run_id, evidence: { root: "core", path: `${authorityRelative(outRoot)}/captures/${coordinate.shell}/${coordinate.run_id}.png`, sha256: "0".repeat(64) }, sidecar: { root: "core", path: `${authorityRelative(outRoot)}/captures/${coordinate.shell}/${coordinate.run_id}.png.sidecar.json`, sha256: "0".repeat(64) } }]));
  const previewBatchId = canonicalBatchId(input.id, command, previewMembers);
  const plan = {
    schema: "omi.polish.native-fixture-batch-plan/v1",
    batch_id_preview: previewBatchId,
    manifest_sha256: manifestHash,
    source_shas: manifest.source_shas,
    input_set_id: input.id,
    command,
    shell,
    offset,
    limit,
    coordinate_count: coordinates.length,
    build_once: ["macos", "ios"].filter((name) => coordinates.some((coordinate) => coordinate.shell === name)),
    coordinates: coordinates.map((coordinate) => ({ run_id: coordinate.run_id, shell: coordinate.shell, device: coordinate.device, viewport: coordinate.viewport, surface_query: coordinate.surface_query, kind: coordinate.kind })),
    authority: { fixture: true, bridge: "disabled", credentials: false, production_api: false, origins: { macos: "http://127.0.0.1:5290", ios: "omi-ui://local" } },
    replay_proof: Boolean(args.replay_proof),
    prepared_input_set: args.prepare ? null : authorityRelative(preparedPath),
    estimated_seconds: estimatedSeconds,
  };
  if (args.dry_run) { console.log(JSON.stringify(plan, null, 2)); return; }
  const batchBuildId = previewBatchId;
  const artifacts = {};
  if (args.prepare) {
    if (coordinates.some((coordinate) => coordinate.shell === "macos")) artifacts.macos = buildMac(manifest, outRoot, batchBuildId);
    if (coordinates.some((coordinate) => coordinate.shell === "ios")) artifacts.ios = buildIos(manifest, outRoot, batchBuildId);
    const preparedDescriptor = writePreparedInputSet(preparedPath, manifestPath, manifest, shellCoordinates, outRoot, shell, artifacts);
    preparedDescriptor.input_set = inputSet(manifestPath, artifacts);
    writeAtomic(preparedPath, preparedDescriptor);
    const preparedInput = inputSet(manifestPath, artifacts, [preparedPath]);
    for (const artifact of Object.values(artifacts)) cleanupEnvironment(artifact.env);
    process.stdout.write(`NATIVE_FIXTURE_PREPARED: ${preparedInput.id} coordinates=${coordinates.length} file=${authorityRelative(preparedPath)}\n`);
    return;
  }
  const prepared = loadPreparedInputSet(preparedPath, manifestPath, manifest, shell);
  input = prepared.input;
  const loadedArtifacts = prepared.artifacts;
  Object.assign(artifacts, loadedArtifacts);
  const startedAt = new Date().toISOString();
  const captureStarted = process.hrtime.bigint();
  try {
    if (artifacts.ios) prepareIosArtifact(artifacts.ios, coordinates);
  } catch (error) {
    if (artifacts.ios) for (const device of artifacts.ios.frozenDevices) {
      clearIosStatusBar(device, artifacts.ios.env);
      restoreIosDevice(device, artifacts.ios);
    }
    for (const artifact of Object.values(artifacts)) cleanupEnvironment(artifact.env);
    throw error;
  }
  const capturesRoot = path.join(outRoot, "captures");
  mkdirSync(capturesRoot, { recursive: true });
  const records = [];
  try {
    for (const coordinate of coordinates) {
    const dir = path.join(capturesRoot, coordinate.shell);
    mkdirSync(dir, { recursive: true });
    const output = path.join(dir, `${coordinate.run_id}.png`);
    const sidecar = `${output}.sidecar.json`;
    rmSync(output, { force: true });
    rmSync(sidecar, { force: true });
    try {
      if (coordinate.shell === "macos") captureMac(coordinate, artifacts.macos, output, timeoutSeconds);
      else captureIos(coordinate, artifacts.ios, output, waitSeconds, timeoutSeconds);
      if (!existsSync(output)) fail(`${coordinate.run_id}: native capture did not write a PNG`);
      if (coordinate.shell === "ios") canonicalizeScreenshot(output);
      const image = validateImage(output, coordinate);
      if (args.replay_proof && records.length === 0) {
        const repeatOutput = `${output}.repeat.png`;
        rmSync(repeatOutput, { force: true });
        if (coordinate.shell === "macos") captureMac(coordinate, artifacts.macos, repeatOutput, timeoutSeconds);
        else captureIos(coordinate, artifacts.ios, repeatOutput, waitSeconds, timeoutSeconds);
        if (coordinate.shell === "ios") canonicalizeScreenshot(repeatOutput);
        const repeatImage = validateImage(repeatOutput, coordinate);
        rmSync(repeatOutput, { force: true });
        if (repeatImage.sha256 !== image.sha256) fail(`${coordinate.run_id}: consecutive capture bytes differ under --replay-proof`);
      }
      const record = {
        schema: "omi.polish.native-fixture-coordinate/v1",
        coordinate_index: manifest.coordinates.findIndex((entry) => entry.run_id === coordinate.run_id),
        run_id: coordinate.run_id,
        shell: coordinate.shell,
        domain: coordinate.domain,
        state: coordinate.state,
        theme: coordinate.theme,
        width: coordinate.width,
        accessibility: coordinate.accessibility,
        kind: "screenshot",
        source_shas: manifest.source_shas,
        capture_class: "native_fixture",
        source_tier: "native_shell",
        surface_query: coordinate.surface_query,
        device: coordinate.device,
        viewport: coordinate.viewport,
        authority: { fixture: true, bridge: "disabled", credentials: false, production_api: false, origin: coordinate.shell === "macos" ? "http://127.0.0.1:5290" : "omi-ui://local" },
        evidence: { class: coordinate.shell === "macos" ? "native-webview-snapshot" : "native-simctl-screenshot", image_path: path.relative(outRoot, output), image_sha256: image.sha256, bytes: image.bytes, observed_width: image.width, observed_height: image.height },
        build: { stamp_path: path.relative(outRoot, artifacts[coordinate.shell].stamp), stamp_sha256: existsSync(artifacts[coordinate.shell].stamp) ? hashFile(artifacts[coordinate.shell].stamp) : null },
      };
      writeAtomic(sidecar, {
        schema: "omi.polish.screenshot/v1",
        domain: coordinate.domain,
        shell: coordinate.shell,
        state: coordinate.state,
        theme: coordinate.theme,
        width: coordinate.width,
        accessibility: coordinate.accessibility,
        run_id: coordinate.run_id,
        source_shas: coordinate.source_shas,
        capture_class: coordinate.capture_class,
        source_tier: coordinate.source_tier,
        image_root: "core",
        image_path: authorityRelative(output),
        image_sha256: image.sha256,
      });
      records.push(record);
    } catch (error) {
      rmSync(output, { force: true });
      rmSync(sidecar, { force: true });
      throw error;
    }
    }
  } finally {
    if (artifacts.ios) {
      for (const device of artifacts.ios.frozenDevices) {
        clearIosStatusBar(device, artifacts.ios.env);
        restoreIosDevice(device, artifacts.ios);
      }
    }
    for (const artifact of Object.values(artifacts)) cleanupEnvironment(artifact.env);
  }
  const elapsedSeconds = Number(process.hrtime.bigint() - captureStarted) / 1e9;
  if (elapsedSeconds > timeoutSeconds) fail(`capture command exceeded timeout (${elapsedSeconds.toFixed(3)}s > ${timeoutSeconds}s)`);
  const members = Object.fromEntries(records.map((record, index) => [`m${String(index).padStart(4, "0")}`, {
    coordinate: [record.kind, record.domain, record.shell, record.state, record.theme, record.width, record.accessibility],
    run_id: record.run_id,
    evidence: { root: "core", path: authorityRelative(path.join(capturesRoot, record.shell, `${record.run_id}.png`)), sha256: record.evidence.image_sha256 },
    sidecar: { root: "core", path: authorityRelative(path.join(capturesRoot, record.shell, `${record.run_id}.png.sidecar.json`)), sha256: hashFile(path.join(capturesRoot, record.shell, `${record.run_id}.png.sidecar.json`)) },
  }]));
  // Each bounded range owns a stable result path. Reusing one generic file
  // would make an earlier batch receipt false as soon as the next range ran.
  const resultPath = path.join(outRoot, `batch-result-${shell}-${offset}-${limit}.json`);
  const captureArgv = ["node", "shells/tools/capture-native-fixture-batch.mjs", "--manifest", authorityRelative(manifestPath), "--out-root", authorityRelative(outRoot), "--shell", shell, "--offset", String(offset), "--limit", String(limit), "--prepared-input-set", authorityRelative(preparedPath), ...(args.replay_proof ? ["--replay-proof"] : []), "--timeout-seconds", String(timeoutSeconds), "--wait-seconds", String(waitSeconds)];
  const stdoutLine = `NATIVE_FIXTURE_BATCH_COMPLETE members=${records.length}\n`;
  const result = {
    schema: "omi.polish.native-fixture-batch-result/v1",
    source_shas: manifest.source_shas,
    manifest_path: `core:${authorityRelative(manifestPath)}`,
    manifest_sha256: manifestHash,
    command,
    argv: captureArgv,
    input_set: input,
    members,
    coordinate_count: records.length,
    timeout_seconds: timeoutSeconds,
    wait_seconds: waitSeconds,
    stdout_sha256: sha256(stdoutLine),
    stderr_sha256: sha256(""),
    authority: plan.authority,
    replay_proof: Boolean(args.replay_proof),
  };
  writeAtomic(resultPath, result);
  process.stdout.write(stdoutLine);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { main(); } catch (error) { console.error(`ERROR: ${error.message}`); process.exitCode = 2; }
}
