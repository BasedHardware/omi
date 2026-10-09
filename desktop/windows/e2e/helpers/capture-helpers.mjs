/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain-JS helper shared with the capture CLI */
// Shared UI-evidence capture for the Windows Electron app.
//
// Specs and scripts/capture-evidence.mjs both call captureEvidence(). Filenames
// and evidence.json follow the repo UI evidence contract:
//   .agent-artifacts/ui-evidence/<dir>/<NNN>-desktop-windows-<slug>.png
// Image bytes are never inspected — only the filename and the manifest entry.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'

export const PLATFORM = 'desktop-windows'
export const SLUG_MAX = 40
export const EVIDENCE_VERSION = 1
export const CAPTURED_BY = 'agent'
export const EVIDENCE_SOURCE = 'playwright-e2e'

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/
const FILE_RE = /^(\d{3})-desktop-windows-([a-z0-9]+(?:-[a-z0-9]+)*)\.png$/
const OUT_RE = /^\.agent-artifacts\/ui-evidence\/([a-z0-9]+(?:-[a-z0-9]+)*)$/
const ROUTE_PATH_RE = /^\/[a-z0-9]+(?:[/-][a-z0-9]+)*$/

/** Zero-pad an ordinal into the contract's 001–999 range. */
export function formatOrdinal(ordinal) {
  const raw = String(ordinal ?? '').trim()
  if (!/^\d+$/.test(raw)) {
    throw new Error(`ordinal must be an integer from 1 to 999, got ${JSON.stringify(ordinal)}`)
  }
  const n = Number(raw)
  if (n < 1 || n > 999) {
    throw new Error(`ordinal must be an integer from 1 to 999, got ${JSON.stringify(ordinal)}`)
  }
  return String(n).padStart(3, '0')
}

/** Lowercase kebab-case screen slug, at most 40 characters. */
export function assertSlug(slug) {
  if (typeof slug !== 'string' || !SLUG_RE.test(slug) || slug.length > SLUG_MAX) {
    throw new Error(
      `slug must be lowercase kebab-case, at most ${SLUG_MAX} characters, got ${JSON.stringify(slug)}`
    )
  }
  return slug
}

/**
 * Reject anything that is not `<NNN>-desktop-windows-<slug>.png`.
 * NNN is 001–999; the slug is lowercase kebab-case ≤40 chars.
 */
export function assertEvidenceFileName(file) {
  if (typeof file !== 'string') {
    throw new Error(`evidence filename must be a string, got ${typeof file}`)
  }
  const match = FILE_RE.exec(file)
  if (!match || match[1] === '000' || match[2].length > SLUG_MAX) {
    throw new Error(
      `evidence filename must match <NNN>-desktop-windows-<slug>.png (NNN from 001, slug lowercase kebab ≤${SLUG_MAX}), got ${JSON.stringify(file)}`
    )
  }
  return { ordinal: Number(match[1]), slug: match[2], file }
}

/** Build a contract filename from an ordinal and a slug. */
export function evidenceFileName(ordinal, slug) {
  const file = `${formatOrdinal(ordinal)}-${PLATFORM}-${assertSlug(slug)}.png`
  return assertEvidenceFileName(file).file
}

/**
 * Repo-relative evidence directory:
 * `.agent-artifacts/ui-evidence/<pr-number-or-branch-slug>`.
 * The directory segment is one lowercase kebab-case name (no slashes).
 */
export function assertEvidenceOutRel(rel) {
  if (typeof rel !== 'string') {
    throw new Error('--out must be a repo-relative .agent-artifacts/ui-evidence/<dir> path')
  }
  const normalized = rel.trim().replace(/\\/g, '/').replace(/\/+$/, '')
  if (!OUT_RE.test(normalized)) {
    throw new Error(
      '--out must be a repo-relative .agent-artifacts/ui-evidence/<dir> path ' +
        `(<dir> is one lowercase kebab-case segment), got ${JSON.stringify(rel)}`
    )
  }
  return normalized
}

/** Normalize `--route` to a hash path the renderer already understands (`#/settings`). */
export function hashForRoute(route) {
  if (typeof route !== 'string' || !route.trim()) {
    throw new Error('--route requires a route name')
  }
  const trimmed = route.trim()
  let hash
  if (trimmed.startsWith('#/')) hash = trimmed
  else if (trimmed.startsWith('/')) hash = `#${trimmed}`
  else if (trimmed.startsWith('#')) {
    throw new Error(
      `--route must be a hash path like settings or #/settings, got ${JSON.stringify(route)}`
    )
  } else hash = `#/${trimmed}`
  const pathOnly = hash.slice(1).split('?')[0]
  if (!ROUTE_PATH_RE.test(pathOnly)) {
    throw new Error(`--route is not a simple app hash route: ${JSON.stringify(route)}`)
  }
  return `#${pathOnly}`
}

function evidenceImage(image) {
  if (!image || typeof image !== 'object') {
    throw new Error('evidence image must be an object')
  }
  const parsed = assertEvidenceFileName(image.file)
  if (image.platform != null && image.platform !== PLATFORM) {
    throw new Error(`platform must be ${PLATFORM}, got ${JSON.stringify(image.platform)}`)
  }
  const description = typeof image.description === 'string' ? image.description.trim() : ''
  if (!description) {
    throw new Error('description must be a non-empty string')
  }
  return {
    file: parsed.file,
    platform: PLATFORM,
    description,
    captured_by: CAPTURED_BY,
    source: EVIDENCE_SOURCE
  }
}

/**
 * Read-modify-write merge: keep every other image, and add or replace by file name.
 * A repeated file name collapses to a single entry in its original position.
 */
export function mergeEvidence(existing, image) {
  const entry = evidenceImage(image)
  if (existing == null) {
    return { version: EVIDENCE_VERSION, images: [entry] }
  }
  if (typeof existing !== 'object' || Array.isArray(existing)) {
    throw new Error('evidence.json must be a JSON object')
  }
  if (existing.version !== EVIDENCE_VERSION) {
    throw new Error(`unsupported evidence.json version: ${JSON.stringify(existing.version)}`)
  }
  if (!Array.isArray(existing.images)) {
    throw new Error('evidence.json images must be an array')
  }
  const images = []
  let replaced = false
  for (const item of existing.images) {
    if (item && typeof item === 'object' && item.file === entry.file) {
      if (!replaced) images.push(entry)
      replaced = true
      continue
    }
    images.push(item)
  }
  if (!replaced) images.push(entry)
  return { ...existing, version: EVIDENCE_VERSION, images }
}

/** JSON, 2-space indent, trailing newline. */
export function serializeEvidence(doc) {
  return `${JSON.stringify(doc, null, 2)}\n`
}

export function evidenceManifestPath(outDir) {
  return path.join(outDir, 'evidence.json')
}

/** `null` when the directory has no manifest yet. */
export function readEvidence(outDir) {
  const manifest = evidenceManifestPath(outDir)
  if (!existsSync(manifest)) return null
  let parsed
  try {
    parsed = JSON.parse(readFileSync(manifest, 'utf8'))
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err)
    throw new Error(`evidence.json is not valid JSON: ${detail}`)
  }
  return parsed
}

export function writeEvidence(outDir, doc) {
  mkdirSync(outDir, { recursive: true })
  const manifest = evidenceManifestPath(outDir)
  writeFileSync(manifest, serializeEvidence(doc))
  return manifest
}

/** Load the sibling manifest (if any), merge one image, and write it back. */
export function upsertEvidence(outDir, image) {
  const doc = mergeEvidence(readEvidence(outDir), image)
  writeEvidence(outDir, doc)
  return doc
}

/** Next free ordinal (max existing NNN + 1), counting every platform in the manifest. */
export function nextOrdinal(existing) {
  const images = existing?.images ?? []
  let max = 0
  for (const item of images) {
    const file = item?.file
    if (typeof file !== 'string') continue
    const match = /^(\d{3})-/.exec(file)
    if (!match || match[1] === '000') continue
    max = Math.max(max, Number(match[1]))
  }
  if (max >= 999) {
    throw new Error('evidence ordinal space is exhausted (999)')
  }
  return max + 1
}

/**
 * Screenshot `page` into `outDir` and upsert evidence.json.
 * `describe` becomes the manifest description; it defaults to the slug.
 * Callers pass the evidence directory (the CLI rejects paths outside the silo).
 */
export async function captureEvidence(page, { slug, ordinal, describe, outDir } = {}) {
  if (!page || typeof page.screenshot !== 'function') {
    throw new Error('captureEvidence requires a Playwright page')
  }
  if (typeof outDir !== 'string' || !outDir.trim()) {
    throw new Error('outDir is required')
  }
  const file = evidenceFileName(ordinal, slug)
  const description = (describe == null ? slug : String(describe)).trim()
  if (!description) {
    throw new Error('description must be a non-empty string')
  }
  const imagePath = path.join(outDir, file)
  mkdirSync(outDir, { recursive: true })
  await page.screenshot({ path: imagePath })
  const evidence = upsertEvidence(outDir, { file, description })
  return { file, path: imagePath, evidence }
}
