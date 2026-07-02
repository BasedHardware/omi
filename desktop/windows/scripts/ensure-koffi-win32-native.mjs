import { copyFileSync, mkdirSync, readFileSync, statSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

if (process.platform !== 'win32') {
  console.log('[ensure-koffi-win32-native] skipped: Windows-only native staging')
  process.exit(0)
}

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const requireFromRoot = createRequire(join(projectRoot, 'package.json'))
const koffiEntry = requireFromRoot.resolve('koffi')
const koffiRoot = dirname(koffiEntry)
const koffiRequire = createRequire(koffiEntry)

const readJson = (file) => JSON.parse(readFileSync(file, 'utf8'))
const koffiPackage = readJson(join(koffiRoot, 'package.json'))

let nativePackageJson
let source
try {
  const nativeEntry = koffiRequire.resolve('@koromix/koffi-win32-x64')
  nativePackageJson = join(dirname(nativeEntry), 'package.json')
  source = join(dirname(nativeEntry), 'win32_x64', 'koffi.node')
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
