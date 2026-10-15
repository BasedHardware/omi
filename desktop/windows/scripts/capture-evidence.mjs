// One-command UI evidence capture for the built Windows/Electron app.
//
// Launches out/main/index.js the same way e2e/bar.spec.mjs does: Playwright
// _electron.launch, OMI_E2E=1, and a throwaway --user-data-dir. OMI_E2E_FAKE_AUTH
// is also set so --route lands in the authed shell — without it App.tsx sends
// every app hash to /login on a fresh profile.
//
//   pnpm capture:evidence -- \
//     --out .agent-artifacts/ui-evidence/<pr-or-branch-slug> \
//     --slug <screen-slug> [--ordinal N] [--describe <text>] \
//     [--route <route-name>] [--settle <ms>]
//
// Build first (from desktop/windows): pnpm run build
import { _electron as electron } from 'playwright'
import { existsSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import {
  assertEvidenceOutRel,
  assertSlug,
  captureEvidence,
  formatOrdinal,
  hashForRoute,
  nextOrdinal,
  readEvidence
} from '../e2e/helpers/capture-helpers.mjs'

const windowsRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = path.resolve(windowsRoot, '..', '..')
const mainEntry = path.join(windowsRoot, 'out', 'main', 'index.js')

const DEFAULT_SETTLE_MS = 500
const SECONDARY_HASHES = ['#/bar', '#/insight-toast', '#/capture', '#/glow']

const baseEnv = {
  ...process.env,
  OMI_E2E: '1',
  OMI_E2E_FAKE_AUTH: '1',
  OMI_AUTOMATION: '0',
  OMI_SKIP_TUNNEL: '1'
}

function usage() {
  return `Usage: pnpm capture:evidence -- --out <repo-relative .agent-artifacts/ui-evidence/<dir>> --slug <screen-slug> [--ordinal N] [--describe <text>] [--route <route-name>] [--settle <ms>]

Captures one screenshot of the built Electron app into the UI evidence silo.
<dir> is a PR number or lowercase kebab-case branch slug. The slug is lowercase kebab-case, at most 40 characters.
Build first: pnpm run build`
}

function parseSettle(raw) {
  if (!/^\d+$/.test(raw)) {
    throw new Error(
      `--settle must be an integer number of milliseconds, got ${JSON.stringify(raw)}`
    )
  }
  const ms = Number(raw)
  if (ms > 60000) throw new Error('--settle must be <= 60000')
  return ms
}

function takeValue(argv, index, flag) {
  const value = argv[index + 1]
  if (value == null || value.startsWith('--')) {
    throw new Error(`${flag} requires a value`)
  }
  return value
}

export function parseArgs(argv) {
  if (argv.includes('--help') || argv.includes('-h')) return { help: true }
  const args = {
    out: null,
    slug: null,
    ordinal: null,
    describe: null,
    route: null,
    settle: DEFAULT_SETTLE_MS
  }
  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i]
    switch (flag) {
      case '--out':
        args.out = assertEvidenceOutRel(takeValue(argv, i, flag))
        i++
        break
      case '--slug':
        args.slug = assertSlug(takeValue(argv, i, flag))
        i++
        break
      case '--ordinal':
        args.ordinal = Number(formatOrdinal(takeValue(argv, i, flag)))
        i++
        break
      case '--describe':
        args.describe = takeValue(argv, i, flag)
        i++
        break
      case '--route':
        args.route = hashForRoute(takeValue(argv, i, flag))
        i++
        break
      case '--settle':
        args.settle = parseSettle(takeValue(argv, i, flag))
        i++
        break
      default:
        throw new Error(`unknown argument: ${flag}`)
    }
  }
  if (!args.out) throw new Error('--out is required')
  if (!args.slug) throw new Error('--slug is required')
  if (args.describe != null && !String(args.describe).trim()) {
    throw new Error('description must be a non-empty string')
  }
  return args
}

function isSecondaryUrl(url) {
  return SECONDARY_HASHES.some((hash) => url.includes(hash))
}

async function waitForReadyPage(app, secondaryHash) {
  await app.firstWindow()
  for (let i = 0; i < 100; i++) {
    const page = (await app.windows()).find((candidate) => {
      const url = candidate.url()
      return secondaryHash ? url.includes(secondaryHash) : !isSecondaryUrl(url)
    })
    if (page) {
      const ready = await page
        .evaluate(() => (document.querySelector('#root')?.childElementCount ?? 0) > 0)
        .catch(() => false)
      if (ready) return page
    }
    await new Promise((resolve) => setTimeout(resolve, 100))
  }
  throw new Error(
    secondaryHash ? `window ${secondaryHash} never became ready` : 'main window shell never mounted'
  )
}

async function navigate(page, hash) {
  await page.evaluate((next) => {
    window.location.hash = next
  }, hash)
  await page.waitForFunction((next) => window.location.hash.split('?')[0] === next, hash, {
    timeout: 10000
  })
}

function isDirectRun() {
  const entry = process.argv[1]
  if (!entry) return false
  try {
    return import.meta.url === pathToFileURL(entry).href
  } catch {
    return false
  }
}

export async function main(argv = process.argv.slice(2)) {
  let args
  try {
    args = parseArgs(argv)
  } catch (err) {
    console.error(err instanceof Error ? err.message : String(err))
    console.error(usage())
    process.exit(1)
  }
  if (args.help) {
    console.log(usage())
    return
  }
  if (!existsSync(mainEntry)) {
    console.error(`missing built main process: ${mainEntry}`)
    console.error('build first: pnpm run build')
    process.exit(1)
  }
  if (!existsSync(path.join(repoRoot, 'desktop', 'windows', 'package.json'))) {
    throw new Error(`could not resolve the repo root from capture-evidence.mjs (got ${repoRoot})`)
  }
  const relativeOut = args.out
  const outDir = path.resolve(repoRoot, relativeOut)
  const escaped = path.relative(repoRoot, outDir)
  if (escaped.startsWith('..') || path.isAbsolute(escaped)) {
    throw new Error(`--out escapes the repo: ${relativeOut}`)
  }
  // Resolve the ordinal before launch so a corrupt manifest fails without Electron.
  const ordinal = args.ordinal ?? nextOrdinal(readEvidence(outDir))

  const userDataDir = mkdtempSync(path.join(tmpdir(), 'omi-capture-evidence-'))
  let app
  try {
    app = await electron.launch({
      args: [mainEntry, `--user-data-dir=${userDataDir}`],
      env: baseEnv
    })
    const secondaryHash =
      args.route && SECONDARY_HASHES.some((hash) => args.route === hash) ? args.route : null
    const page = await waitForReadyPage(app, secondaryHash)
    if (args.route && !secondaryHash) await navigate(page, args.route)
    if (args.settle > 0) await new Promise((resolve) => setTimeout(resolve, args.settle))
    const result = await captureEvidence(page, {
      slug: args.slug,
      ordinal,
      describe: args.describe,
      outDir
    })
    console.log(`${relativeOut}/${result.file}`)
  } finally {
    if (app) {
      try {
        await app.close()
      } catch {
        /* already closed */
      }
    }
    try {
      rmSync(userDataDir, { recursive: true, force: true })
    } catch {
      /* best-effort */
    }
  }
}

if (isDirectRun()) {
  main().catch((err) => {
    console.error(err instanceof Error ? err.message : String(err))
    process.exit(1)
  })
}
