import { copyFileSync, existsSync, mkdirSync, readFileSync, statSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')

// This stages the Windows x64 native module for packaging. On other platforms
// the @koromix/koffi-win32-x64 optional dependency is never installed, so skip
// instead of failing `pnpm install` for macOS/Linux contributors. Set
// OMI_REQUIRE_KOFFI_WIN32=1 to force the check anywhere (e.g. Windows CI).
if (process.platform !== 'win32' && process.env.OMI_REQUIRE_KOFFI_WIN32 !== '1') {
  console.log(
    `[ensure-koffi-win32-native] skipping on ${process.platform} (only needed for Windows packaging)`
  )
  process.exit(0)
}

const readJson = (file) => JSON.parse(readFileSync(file, 'utf8'))

// Resolve a package's package.json even when its `exports` map does not expose
// "./package.json" (koffi's does not — require.resolve('koffi/package.json')
// throws ERR_PACKAGE_PATH_NOT_EXPORTED). Fall back to resolving the entry
// point and walking up until the package's own package.json is found.
const resolvePackageJson = (require, name) => {
  try {
    return require.resolve(`${name}/package.json`)
  } catch (error) {
    if (error?.code !== 'ERR_PACKAGE_PATH_NOT_EXPORTED') throw error
  }
  let dir = dirname(require.resolve(name))
  for (;;) {
    const candidate = join(dir, 'package.json')
    if (existsSync(candidate) && readJson(candidate).name === name) return candidate
    const parent = dirname(dir)
    if (parent === dir) throw new Error(`Cannot locate package.json for ${name}`)
    dir = parent
  }
}

const requireFromRoot = createRequire(join(projectRoot, 'package.json'))
const koffiPackageJson = resolvePackageJson(requireFromRoot, 'koffi')
const koffiRequire = createRequire(koffiPackageJson)

const koffiPackage = readJson(koffiPackageJson)

let nativePackageJson
let source
try {
  nativePackageJson = resolvePackageJson(koffiRequire, '@koromix/koffi-win32-x64')
  source = join(dirname(nativePackageJson), 'win32_x64', 'koffi.node')
} catch (error) {
  throw new Error(
    [
      'Missing @koromix/koffi-win32-x64.',
      'Run npm install from desktop/windows on Windows so npm installs win32/x64 optional dependencies.'
    ].join(' '),
    { cause: error }
  )
}

const nativePackage = readJson(nativePackageJson)
if (nativePackage.version !== koffiPackage.version) {
  throw new Error(
    `Koffi native package version mismatch: koffi=${koffiPackage.version}, @koromix/koffi-win32-x64=${nativePackage.version}`
  )
}

const sourceSize = statSync(source).size
if (sourceSize <= 0) {
  throw new Error(`Koffi native module is empty: ${source}`)
}

const targetDir = join(projectRoot, 'resources', 'koffi', 'win32_x64')
const target = join(targetDir, 'koffi.node')
mkdirSync(targetDir, { recursive: true })
copyFileSync(source, target)
console.log(`[ensure-koffi-win32-native] staged ${target} (${sourceSize} bytes)`)
