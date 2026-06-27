/**
 * Copies the platform-specific koffi.node prebuilt binary from pnpm's virtual
 * store into node_modules/koffi/build/koffi/<triplet>/, which is one of koffi's
 * own runtime search paths and is already covered by asarUnpack: node_modules/koffi/**.
 *
 * Why this is needed: pnpm with node-linker=hoisted does not hoist optional
 * scoped deps like @koromix/koffi-win32-x64 to top-level node_modules/, so
 * koffi's static require('@koromix/...') fails. The binary only lives in the
 * .pnpm/ virtual store. This script bridges the gap before electron-builder
 * packages the app.
 */

import { existsSync, cpSync, mkdirSync, readdirSync } from 'fs'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = join(__dirname, '..')
const pnpmStore = join(root, 'node_modules', '.pnpm')

const platform = process.platform // e.g. win32
const arch = process.arch // e.g. x64
const triplet = `${platform}_${arch}` // e.g. win32_x64
const scopedPkg = `koffi-${platform}-${arch}` // e.g. koffi-win32-x64
const storePrefix = `@koromix+${scopedPkg}` // e.g. @koromix+koffi-win32-x64

let srcNode = null

if (existsSync(pnpmStore)) {
  for (const entry of readdirSync(pnpmStore)) {
    if (!entry.startsWith(storePrefix)) continue
    const candidate = join(
      pnpmStore,
      entry,
      'node_modules',
      '@koromix',
      scopedPkg,
      triplet,
      'koffi.node'
    )
    if (existsSync(candidate)) {
      srcNode = candidate
      break
    }
  }
}

if (!srcNode) {
  console.error(
    `[copy-koffi] ERROR: Cannot find koffi.node for ${triplet} in ${pnpmStore}\n` +
      `  Expected a directory matching: ${storePrefix}@*/node_modules/@koromix/${scopedPkg}/${triplet}/koffi.node`
  )
  process.exit(1)
}

const dest = join(root, 'node_modules', 'koffi', 'build', 'koffi', triplet, 'koffi.node')
mkdirSync(dirname(dest), { recursive: true })
cpSync(srcNode, dest)
console.log(
  `[copy-koffi] OK: copied koffi.node (${triplet}) → node_modules/koffi/build/koffi/${triplet}/`
)
