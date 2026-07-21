import { closeSync, openSync, readSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const MIN_PE_SIZE = 1024
const packageRoots =
  process.argv.length > 2
    ? process.argv.slice(2).map((path) => resolve(path))
    : [join(projectRoot, 'dist', 'win-unpacked')]

const verifyPeFile = (file) => {
  const stat = statSync(file)
  if (stat.size < MIN_PE_SIZE) {
    throw new Error(`Koffi native module is empty: ${file}`)
  }

  const fd = openSync(file, 'r')
  const dosHeader = Buffer.alloc(64)
  try {
    readSync(fd, dosHeader, 0, dosHeader.length, 0)
    if (dosHeader.subarray(0, 2).toString('ascii') !== 'MZ') {
      throw new Error(`Koffi native module is not a Windows binary: ${file}`)
    }

    const peOffset = dosHeader.readUInt32LE(0x3c)
    if (peOffset <= 0 || peOffset > stat.size - 4) {
      throw new Error(`Koffi native module has an invalid PE header offset: ${file}`)
    }

    const peSignature = Buffer.alloc(4)
    readSync(fd, peSignature, 0, peSignature.length, peOffset)
    if (peSignature.toString('binary') !== 'PE\u0000\u0000') {
      throw new Error(`Koffi native module is missing a PE signature: ${file}`)
    }
  } finally {
    closeSync(fd)
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
