// Print the resolved dev instance for the current checkout as JSON (or a human
// line with --human). Used by bootstrap-worktree.ps1 and handy for `pnpm dev:instance`.
import { resolveInstance } from './lib/dev-ports.mjs'

const inst = resolveInstance(process.cwd())
if (process.argv.includes('--human')) {
  console.log(
    inst.isPrimary
      ? `primary checkout — renderer http://localhost:${inst.rendererPort}, CDP ${inst.cdpPort}`
      : `instance "${inst.name}" — renderer http://localhost:${inst.rendererPort}, CDP ${inst.cdpPort}, profile omi-windows-sandbox-${inst.name}`
  )
} else {
  console.log(JSON.stringify(inst))
}
