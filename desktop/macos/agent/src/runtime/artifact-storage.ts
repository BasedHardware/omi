import { createHash } from "node:crypto";
import { copyFileSync, cpSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import type { AdapterArtifactReference } from "../adapters/interface.js";

export interface ArtifactStorageScope {
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
}

export interface ArtifactStorageOptions {
  rootDir?: string;
}

export class OmiArtifactStorage {
  readonly rootDir: string;

  constructor(options: ArtifactStorageOptions = {}) {
    this.rootDir = resolve(options.rootDir ?? defaultArtifactRoot());
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
      if (entry.name === "manifest.json" || (!entry.isFile() && !entry.isDirectory())) {
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
