import { closeSync, openSync, readSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const packageRoots =
  process.argv.length > 2
    ? process.argv.slice(2).map((path) => resolve(path))
    : [join(projectRoot, 'dist', 'win-unpacked')]

const verifyPeFile = (file) => {
  const stat = statSync(file)
  if (stat.size <= 0) {
    throw new Error(`Koffi native module is empty: ${file}`)
  }

  const fd = openSync(file, 'r')
  const header = Buffer.alloc(2)
  try {
    readSync(fd, header, 0, 2, 0)
  } finally {
    closeSync(fd)
  }
  if (header.toString('ascii') !== 'MZ') {
    throw new Error(`Koffi native module is not a Windows binary: ${file}`)
  }
  return stat.size
}

const tried = []
for (const root of packageRoots) {
  const file = join(root, 'resources', 'koffi', 'win32_x64', 'koffi.node')
  tried.push(file)
  try {
    const size = verifyPeFile(file)
    console.log(`[verify-win-koffi-native] found ${file} (${size} bytes)`)
    process.exit(0)
  } catch (error) {
    if (error.code !== 'ENOENT') throw error
  }
}

throw new Error(`Missing packaged Koffi native module. Checked: ${tried.join(', ')}`)
