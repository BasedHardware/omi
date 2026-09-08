// Build the app, then run the DB-corruption-recovery E2E against the real built
// main process (and therefore the real better-sqlite3 driver, which plain-node
// vitest cannot load). Hermetic: throwaway --user-data-dir + OMI_DB_PATH.
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const NO_BUILD = process.argv.includes('--no-build')

if (!NO_BUILD) {
  execFileSync('npx', ['electron-vite', 'build'], { stdio: 'inherit', cwd: root, shell: true })
}

execFileSync('node', ['--test', '--test-timeout=90000', 'e2e/db-recovery.spec.mjs'], {
  stdio: 'inherit',
  cwd: root
})
