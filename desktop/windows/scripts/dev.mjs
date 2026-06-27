/* eslint-disable @typescript-eslint/explicit-function-return-type */
import { spawn } from 'node:child_process'
import { dirname, join } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const env = { ...process.env }
const args = ['dev', ...process.argv.slice(2)]
const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const electronVite = join(
  root,
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'electron-vite.cmd' : 'electron-vite'
)

if (env.ELECTRON_RUN_AS_NODE) {
  console.warn(
    '[dev] ELECTRON_RUN_AS_NODE is set; unsetting it for Electron.\n' +
      '[dev] Electron needs to run as an app here, not as the Node runtime.'
  )
  delete env.ELECTRON_RUN_AS_NODE
}

const child = spawn(electronVite, args, {
  env,
  shell: true,
  stdio: 'inherit'
})

/**
 * @param {NodeJS.Signals} signal
 * @returns {void}
 */
const forwardSignal = (signal) => {
  if (!child.killed) child.kill(signal)
}

process.on('SIGINT', () => forwardSignal('SIGINT'))
process.on('SIGTERM', () => forwardSignal('SIGTERM'))

child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal)
  process.exit(code ?? 1)
})
