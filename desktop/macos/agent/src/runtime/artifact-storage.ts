import { createHash } from "node:crypto";
import { copyFileSync, cpSync, existsSync, lstatSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import type { AdapterArtifactReference } from "../adapters/interface.js";
import { isDeniedManagedRunArtifactBasename } from "./artifact-filters.js";

export interface ArtifactStorageScope {
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
}

export interface ArtifactStorageOptions {
  rootDir?: string;
  /** Overrides the signed-in Desktop root in isolated integration tests. */
  reportedDesktopRoots?: readonly string[];
}

export class OmiArtifactStorage {
  readonly rootDir: string;
  private readonly temporaryArtifactRoots: readonly string[];
  private readonly reportedDesktopRoots: readonly string[];

  constructor(options: ArtifactStorageOptions = {}) {
    this.rootDir = resolve(options.rootDir ?? defaultArtifactRoot());
    this.reportedDesktopRoots = uniqueResolvedPaths(options.reportedDesktopRoots ?? [join(homedir(), "Desktop")]);
    this.temporaryArtifactRoots = uniqueResolvedPaths([
      "/tmp",
      "/private/tmp",
      tmpdir(),
    ]);
  }

  normalizeArtifact(
    artifact: AdapterArtifactReference,
    scope: ArtifactStorageScope
  ): AdapterArtifactReference {
    if (shouldKeepExternalLocation(artifact)) {
      return artifact;
    }
    if (!artifact.uri.startsWith("file://")) {
      return artifact;
    }

    const sourcePath = fileURLToPath(artifact.uri);
    if (!existsSync(sourcePath)) {
      return artifact;
    }

    const sourceStat = statSync(sourcePath);
    const destinationDir = this.directoryFor(scope);
    mkdirSync(destinationDir, { recursive: true });

    const destinationPath = uniqueDestinationPath(
      destinationDir,
      sanitizeFileName(artifact.displayName || basename(sourcePath) || "artifact")
    );

    if (isInside(sourcePath, this.rootDir)) {
      const normalizedMetadata = {
        ...(artifact.metadata ?? {}),
        omiManaged: true,
        managedPath: sourcePath,
      };
      return {
        ...artifact,
        uri: pathToFileURL(sourcePath).toString(),
        displayName: artifact.displayName ?? basename(sourcePath),
        sizeBytes: artifact.sizeBytes ?? (sourceStat.isFile() ? sourceStat.size : null),
        contentHash: artifact.contentHash ?? (sourceStat.isFile() ? fileHash(sourcePath) : null),
        metadata: normalizedMetadata,
      };
    }

    if (sourceStat.isDirectory()) {
      cpSync(sourcePath, destinationPath, { recursive: true, force: false, errorOnExist: true });
    } else {
      copyFileSync(sourcePath, destinationPath);
    }

    const copiedStat = statSync(destinationPath);
    const metadata = {
      ...(artifact.metadata ?? {}),
      omiManaged: true,
      originalUri: artifact.uri,
      managedPath: destinationPath,
    };

    this.writeManifest(destinationDir, {
      artifact,
      managedUri: pathToFileURL(destinationPath).toString(),
      managedPath: destinationPath,
      originalUri: artifact.uri,
      scope,
      copiedAtMs: Date.now(),
    });

    return {
      ...artifact,
      uri: pathToFileURL(destinationPath).toString(),
      displayName: artifact.displayName ?? basename(destinationPath),
      sizeBytes: artifact.sizeBytes ?? (copiedStat.isFile() ? copiedStat.size : null),
      contentHash: artifact.contentHash ?? (copiedStat.isFile() ? fileHash(destinationPath) : null),
      metadata,
    };
  }

  prepareRunDirectory(scope: ArtifactStorageScope): string {
    const directory = this.directoryFor(scope);
    mkdirSync(directory, { recursive: true });
    return directory;
  }

  isRootDirectory(path: string | undefined | null): boolean {
    return path ? resolve(path) === this.rootDir : false;
  }

  discoverRunArtifacts(
    scope: ArtifactStorageScope,
    existingArtifacts: readonly Pick<AdapterArtifactReference, "uri">[] = []
  ): AdapterArtifactReference[] {
    const directory = this.directoryFor(scope);
    if (!existsSync(directory)) {
      return [];
    }

    const existingUris = new Set(existingArtifacts.map((artifact) => artifact.uri));
    const discovered: AdapterArtifactReference[] = [];
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      if (
        entry.name === "manifest.json"
        || isDeniedManagedRunArtifactBasename(entry.name)
        || (!entry.isFile() && !entry.isDirectory())
      ) {
        continue;
      }
      const path = join(directory, entry.name);
      const uri = pathToFileURL(path).toString();
      if (existingUris.has(uri)) {
        continue;
      }
      const stat = statSync(path);
      discovered.push({
        kind: entry.isDirectory() ? "directory" : kindForFileName(entry.name),
        role: "result",
        uri,
        displayName: entry.name,
        mimeType: entry.isDirectory() ? "inode/directory" : mimeTypeForFileName(entry.name),
        contentHash: entry.isDirectory() ? null : fileHash(path),
        sizeBytes: entry.isDirectory() ? null : stat.size,
        metadata: {
          omiManaged: true,
          managedPath: path,
          discoveredFromRunDirectory: true,
        },
      });
    }
    return discovered;
  }

  /**
   * Some ACP providers report a finished local deliverable only in their final
   * prose; they do not emit the structured artifact event used by the normal
   * adapter path. Recover that narrow, user-visible case without treating every
   * pathname mentioned in model text as an artifact.
   *
   * Absolute paths are eligible only under a temporary directory, covering
   * providers that do not honor Omi's managed working directory convention.
   * Desktop uses its own stricter delivery grammar ("I built file.html on your
   * Desktop" or "file.html was built on the Desktop"), which resolves only a
   * simple filename beneath the signed-in user's Desktop.
   * Neither path lets a completion import arbitrary user files merely because
   * it names their paths.
   */
  discoverReportedTerminalArtifacts(
    finalText: string,
    existingArtifacts: readonly Pick<AdapterArtifactReference, "uri">[] = []
  ): AdapterArtifactReference[] {
    const existingUris = new Set(existingArtifacts.map((artifact) => artifact.uri));
    const discovered: AdapterArtifactReference[] = [];
    const seenPaths = new Set<string>();

    for (const line of finalText.slice(0, MAX_REPORTED_TERMINAL_TEXT_CHARS).split(/\r?\n/)) {
      const desktopCandidates = reportedDesktopFileCandidates(line, this.reportedDesktopRoots);
      if (!EXPLICIT_ARTIFACT_DELIVERY_LANGUAGE.test(line) && desktopCandidates.length === 0) continue;

      const candidates = [
        ...reportedLocalFileCandidates(line).map((candidate) => ({
          candidate,
          allowedRoots: this.temporaryArtifactRoots,
        })),
        ...desktopCandidates.map((candidate) => ({
          candidate,
          allowedRoots: this.reportedDesktopRoots,
        })),
      ];
      for (const { candidate, allowedRoots } of candidates) {
        const path = localPathFromReportedCandidate(candidate);
        if (!path || !this.isReportableArtifactPath(path, allowedRoots) || seenPaths.has(path)) continue;
        seenPaths.add(path);

        const uri = pathToFileURL(path).toString();
        if (existingUris.has(uri)) continue;

        try {
          const stat = lstatSync(path);
          if ((!stat.isFile() && !stat.isDirectory()) || stat.isSymbolicLink()) continue;
          const displayName = basename(path);
          if (!displayName || isDeniedManagedRunArtifactBasename(displayName)) continue;
          discovered.push({
            kind: stat.isDirectory() ? "directory" : kindForFileName(displayName),
            role: "result",
            uri,
            displayName,
            mimeType: stat.isDirectory() ? "inode/directory" : mimeTypeForFileName(displayName),
            contentHash: stat.isDirectory() ? null : fileHash(path),
            sizeBytes: stat.isDirectory() ? null : stat.size,
            metadata: { discoveredFromTerminalReport: true },
          });
        } catch {
          // A terminal report is advisory. Skip files that disappeared or cannot
          // be read between the provider's completion and kernel finalization.
        }

        if (discovered.length >= MAX_REPORTED_TERMINAL_ARTIFACTS) return discovered;
      }
    }
    return discovered;
  }

  private isReportableArtifactPath(path: string, allowedRoots: readonly string[]): boolean {
    return allowedRoots.some((root) => path !== root && isInside(path, root));
  }

  directoryFor(scope: ArtifactStorageScope): string {
    return join(
      this.rootDir,
      sanitizePathComponent(scope.ownerId || "local"),
      sanitizePathComponent(scope.sessionId),
      sanitizePathComponent(scope.runId),
      sanitizePathComponent(scope.attemptId)
    );
  }

  private writeManifest(directory: string, entry: Record<string, unknown>): void {
    const manifestPath = join(directory, "manifest.json");
    let entries: unknown[] = [];
    if (existsSync(manifestPath)) {
      try {
        const raw = String(readFileSync(manifestPath));
        const parsed = JSON.parse(raw);
        entries = Array.isArray(parsed?.artifacts) ? parsed.artifacts : [];
      } catch {
        entries = [];
      }
    }
    writeFileSync(manifestPath, `${JSON.stringify({ artifacts: [...entries, entry] }, null, 2)}\n`);
  }
}

export function defaultArtifactRoot(env: NodeJS.ProcessEnv = process.env): string {
  if (env.OMI_AGENT_ARTIFACTS_DIR) {
    return env.OMI_AGENT_ARTIFACTS_DIR;
  }
  if (env.OMI_AGENT_STATE_DIR) {
    const runtimeRoot = dirname(env.OMI_AGENT_STATE_DIR);
    const bundleComponent = basename(env.OMI_AGENT_STATE_DIR);
    return join(dirname(runtimeRoot), "Artifacts", bundleComponent);
  }
  const bundleId = env.__CFBundleIdentifier || "com.omi.computer-macos";
  return join(homedir(), "Library", "Application Support", "Omi", "Artifacts", bundleId);
}

function shouldKeepExternalLocation(artifact: AdapterArtifactReference): boolean {
  const metadata = artifact.metadata ?? {};
  return metadata.userSpecifiedPath === true
    || metadata.keepExternalLocation === true
    || metadata.omiManaged === false;
}

const MAX_REPORTED_TERMINAL_TEXT_CHARS = 64 * 1024;
const MAX_REPORTED_TERMINAL_ARTIFACTS = 8;
const EXPLICIT_ARTIFACT_DELIVERY_LANGUAGE = /(?:\b(?:file|artifact|deliverable|output|result|report|page|document|site)\b[^\n]{0,120}\b(?:lives?|saved|written|created|generated|produced|ready|available|located)\b|\b(?:saved|written|created|generated|produced)\b[^\n]{0,120}\b(?:file|artifact|deliverable|output|result|report|page|document|site)\b|\b(?:file|artifact|deliverable|output|result|report|page|document|site)\b\s*:)/i;
const REPORTED_LOCAL_FILE_CANDIDATE = /file:\/\/[^\s`<>"']+|\/(?:[^\s`<>"']+)/g;
const REPORTED_DESKTOP_FILE_CANDIDATE = /\b(?:built|created|generated|saved|wrote)\b[^\n]{0,120}?\b([A-Za-z0-9][A-Za-z0-9._-]{0,127})(?:[`*_]+)?\s+on\s+(?:your|the)\s+desktop\b/gi;
const REPORTED_DESKTOP_PASSIVE_FILE_CANDIDATE = /\b([A-Za-z0-9][A-Za-z0-9._-]{0,127})(?:[`*_]+)?\s+(?:was\s+)?(?:built|created|generated|saved|written)\s+on\s+(?:your|the)\s+desktop\b/gi;

function reportedLocalFileCandidates(line: string): string[] {
  return line.match(REPORTED_LOCAL_FILE_CANDIDATE) ?? [];
}

function reportedDesktopFileCandidates(line: string, desktopRoots: readonly string[]): string[] {
  return [
    ...line.matchAll(REPORTED_DESKTOP_FILE_CANDIDATE),
    ...line.matchAll(REPORTED_DESKTOP_PASSIVE_FILE_CANDIDATE),
  ].flatMap((match) => {
    const fileName = match[1];
    return fileName ? desktopRoots.map((root) => join(root, fileName)) : [];
  });
}

function localPathFromReportedCandidate(candidate: string): string | null {
  const trimmed = candidate.replace(/[),.;:!?\]}]+$/g, "");
  try {
    const path = trimmed.startsWith("file://") ? fileURLToPath(trimmed) : trimmed;
    return isAbsolute(path) ? resolve(path) : null;
  } catch {
    return null;
  }
}

function uniqueResolvedPaths(paths: readonly string[]): string[] {
  return [...new Set(paths.map((path) => resolve(path)))];
}

function sanitizePathComponent(value: string): string {
  return sanitizeFileName(value).replace(/^\.+$/, "artifact");
}

function sanitizeFileName(value: string): string {
  const clean = value.replace(/[/:\\\0]/g, "-").trim();
  return clean.length > 0 ? clean : "artifact";
}

function uniqueDestinationPath(directory: string, fileName: string): string {
  const extIndex = fileName.lastIndexOf(".");
  const stem = extIndex > 0 ? fileName.slice(0, extIndex) : fileName;
  const ext = extIndex > 0 ? fileName.slice(extIndex) : "";
  let candidate = join(directory, fileName);
  let index = 2;
  while (existsSync(candidate)) {
    candidate = join(directory, `${stem}-${index}${ext}`);
    index += 1;
  }
  return candidate;
}

function isInside(path: string, root: string): boolean {
  const rel = relative(resolve(root), resolve(path));
  return rel === "" || (!rel.startsWith("..") && !rel.startsWith("/"));
}

function fileHash(path: string): string {
  const hash = createHash("sha256");
  hash.update(readFileSync(path));
  return `sha256:${hash.digest("hex")}`;
}

function kindForFileName(fileName: string): string {
  const ext = extension(fileName);
  switch (ext) {
    case ".md": return "markdown";
    case ".txt": return "text";
    case ".json": return "json";
    case ".csv": return "csv";
    case ".html": return "html";
    case ".png":
    case ".jpg":
    case ".jpeg":
    case ".webp":
    case ".gif":
      return "image";
    default:
      return "file";
  }
}

function mimeTypeForFileName(fileName: string): string {
  const ext = extension(fileName);
  switch (ext) {
    case ".md": return "text/markdown";
    case ".txt": return "text/plain";
    case ".json": return "application/json";
    case ".csv": return "text/csv";
    case ".html": return "text/html";
    case ".png": return "image/png";
    case ".jpg":
    case ".jpeg": return "image/jpeg";
    case ".webp": return "image/webp";
    case ".gif": return "image/gif";
    default: return "application/octet-stream";
  }
}

function extension(fileName: string): string {
  const index = fileName.lastIndexOf(".");
  return index > 0 ? fileName.slice(index).toLowerCase() : "";
}
