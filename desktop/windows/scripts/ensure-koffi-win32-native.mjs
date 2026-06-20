import { copyFileSync, mkdirSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const requireFromRoot = createRequire(join(projectRoot, 'package.json'))
const koffiRequire = createRequire(requireFromRoot.resolve('koffi'))

let source
try {
  source = koffiRequire.resolve('@koromix/koffi-win32-x64/win32_x64/koffi.node')
} catch (error) {
  throw new Error(
    'Missing @koromix/koffi-win32-x64. Run pnpm install with supportedArchitectures win32/x64 enabled.',
    { cause: error }
  )
}

const targetDir = join(projectRoot, 'resources', 'koffi', 'win32_x64')
mkdirSync(targetDir, { recursive: true })
copyFileSync(source, join(targetDir, 'koffi.node'))
console.log('[ensure-koffi-win32-native] copied win32_x64/koffi.node')
