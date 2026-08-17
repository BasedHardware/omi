import { spawn } from 'node:child_process';
import { mkdir, writeFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { sha256File } from './identity.mjs';

export const EVIDENCE_CLASS = Object.freeze({
  WEBVIEW_SNAPSHOT: 'webview_snapshot',
  WINDOW_COMPOSITE: 'window_composite',
  SIMULATOR_CAPTURE: 'simulator_capture',
});

/**
 * @typedef {{class: string, path: string, bytes: number, sha256: string, capturedAt: string, targeting: string}} CaptureResult
 */

/**
 * Default command runner — Node builtins only.
 * @param {string} command
 * @param {string[]} args
 * @returns {Promise<{stdout: string, stderr: string, code: number}>}
 */
export function defaultRunCommand(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });
    child.on('error', reject);
    child.on('close', (code) => {
      resolve({ stdout, stderr, code: code ?? 1 });
    });
  });
}

/**
 * Resolve a CGWindowID for the named app via Swift/CoreGraphics.
 * Returns null when no on-screen window can be identified.
 *
 * @param {string} appName
 * @param {typeof defaultRunCommand} runCommand
 * @returns {Promise<number|null>}
 */
export async function defaultResolveWindowId(appName, runCommand = defaultRunCommand) {
  // Escape for embedding in a Swift double-quoted string.
  const escaped = appName.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  const script = [
    'import Cocoa',
    `let target = "${escaped}"`,
    'let opts = CGWindowListOption(arrayLiteral: .optionOnScreenOnly, .excludeDesktopElements)',
    'guard let info = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]] else { exit(2) }',
    'for w in info {',
    '  let owner = w[kCGWindowOwnerName as String] as? String ?? ""',
    '  let layer = w[kCGWindowLayer as String] as? Int ?? -1',
    '  guard owner == target, layer == 0 else { continue }',
    '  if let num = w[kCGWindowNumber as String] as? Int {',
    '    print(num)',
    '    exit(0)',
    '  }',
    '}',
    'exit(1)',
  ].join('\n');

  const result = await runCommand('/usr/bin/swift', ['-e', script]);
  if (result.code !== 0) return null;
  const id = Number.parseInt(result.stdout.trim(), 10);
  return Number.isFinite(id) ? id : null;
}

/**
 * Ensure the evidence class appears in the basename (self-describing artifact).
 * @param {string} outPath
 * @param {string} evidenceClass
 */
export function bakeClassIntoFilename(outPath, evidenceClass) {
  const dir = path.dirname(outPath);
  const base = path.basename(outPath);
  if (base.includes(evidenceClass)) {
    return outPath;
  }
  return path.join(dir, `${evidenceClass}-${base}`);
}

/**
 * Sidecar path: same basename, `.json` instead of the image extension.
 * @param {string} imagePath
 */
export function sidecarPathFor(imagePath) {
  const parsed = path.parse(imagePath);
  return path.join(parsed.dir, `${parsed.name}.json`);
}

/**
 * @param {string} imagePath
 * @param {object} meta
 */
async function writeSidecar(imagePath, meta) {
  const sidecarPath = sidecarPathFor(imagePath);
  await writeFile(sidecarPath, `${JSON.stringify(meta, null, 2)}\n`, 'utf8');
  return sidecarPath;
}

/**
 * Finalize a capture: hash, size, sidecar, return CaptureResult.
 * @param {object} opts
 * @param {string} opts.evidenceClass
 * @param {string} opts.finalPath
 * @param {string} opts.targeting
 * @param {string} [opts.appName]
 * @param {string} [opts.udid]
 */
async function finalizeCapture({ evidenceClass, finalPath, targeting, appName, udid }) {
  const bytes = (await stat(finalPath)).size;
  const hash = await sha256File(finalPath);
  const capturedAt = new Date().toISOString();
  /** @type {CaptureResult} */
  const result = {
    class: evidenceClass,
    path: finalPath,
    bytes,
    sha256: hash,
    capturedAt,
    targeting,
  };
  await writeSidecar(finalPath, {
    ...result,
    ...(appName !== undefined ? { appName } : {}),
    ...(udid !== undefined ? { udid } : {}),
  });
  return result;
}

/**
 * Capture a named app's window via `/usr/sbin/screencapture`.
 * Prefers `-l <windowId>` when a CGWindowID can be resolved; otherwise
 * captures the display and records `targeting: 'display_fallback'`.
 *
 * @param {object} opts
 * @param {string} opts.appName
 * @param {string} opts.outPath
 * @param {typeof defaultRunCommand} [opts.runCommand]
 * @param {typeof defaultResolveWindowId} [opts.resolveWindowId]
 * @returns {Promise<CaptureResult>}
 */
export async function captureWindow({
  appName,
  outPath,
  runCommand = defaultRunCommand,
  resolveWindowId = defaultResolveWindowId,
}) {
  if (!appName) throw new Error('captureWindow requires appName');
  if (!outPath) throw new Error('captureWindow requires outPath');

  const evidenceClass = EVIDENCE_CLASS.WINDOW_COMPOSITE;
  const finalPath = bakeClassIntoFilename(outPath, evidenceClass);
  await mkdir(path.dirname(finalPath), { recursive: true });

  const windowId = await resolveWindowId(appName, runCommand);
  let targeting;
  let args;
  if (windowId != null) {
    targeting = 'window';
    args = ['-x', '-l', String(windowId), finalPath];
  } else {
    targeting = 'display_fallback';
    args = ['-x', finalPath];
  }

  const result = await runCommand('/usr/sbin/screencapture', args);
  if (result.code !== 0) {
    throw new Error(
      `screencapture failed (code ${result.code}, targeting=${targeting}): ${result.stderr.trim() || result.stdout.trim() || 'no output'}`,
    );
  }

  return finalizeCapture({
    evidenceClass,
    finalPath,
    targeting,
    appName,
  });
}

/**
 * Capture a simulator framebuffer via `xcrun simctl io <udid> screenshot`.
 *
 * @param {object} opts
 * @param {string} opts.udid
 * @param {string} opts.outPath
 * @param {typeof defaultRunCommand} [opts.runCommand]
 * @returns {Promise<CaptureResult>}
 */
export async function captureSimulator({ udid, outPath, runCommand = defaultRunCommand }) {
  if (!udid) throw new Error('captureSimulator requires udid');
  if (!outPath) throw new Error('captureSimulator requires outPath');

  const evidenceClass = EVIDENCE_CLASS.SIMULATOR_CAPTURE;
  const finalPath = bakeClassIntoFilename(outPath, evidenceClass);
  await mkdir(path.dirname(finalPath), { recursive: true });

  const targeting = 'simulator';
  const result = await runCommand('/usr/bin/xcrun', [
    'simctl',
    'io',
    udid,
    'screenshot',
    finalPath,
  ]);
  if (result.code !== 0) {
    throw new Error(
      `simctl screenshot failed (code ${result.code}): ${result.stderr.trim() || result.stdout.trim() || 'no output'}`,
    );
  }

  return finalizeCapture({
    evidenceClass,
    finalPath,
    targeting,
    udid,
  });
}
