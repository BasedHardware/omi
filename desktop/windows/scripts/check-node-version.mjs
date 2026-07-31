// Fail the test run early, and legibly, when Node is outside the supported range.
//
// Without this the failure is silent and deeply confusing: on Node >= 24 the
// runtime ships its own experimental `localStorage` global that is `undefined`
// unless `--localstorage-file` is passed, and it takes precedence over the one
// jsdom installs. Every `// @vitest-environment jsdom` suite that touches
// localStorage then dies with `Cannot read properties of undefined (reading
// 'clear')` — 29 test files and 129 tests on Node 26.3.1, all green on Node
// 22.16.0 with the same code and the same lockfile. CI pins Node 22, so the
// breakage is invisible there and only ever hits a contributor's machine.
//
// The floor is not cosmetic either: `@earendil-works/pi-ai` declares
// `engines.node >= 22.19.0`, so an older 22.x installs but is unsupported.
//
// Kept as a `pretest` hook rather than `engine-strict=true` in .npmrc: that flag
// makes pnpm enforce the engines field of every transitive dependency, which is a
// far larger blast radius than the problem this guards.

const RANGE = '>=22.19.0 <23'

const [major, minor] = process.versions.node.split('.').map(Number)
const supported = major === 22 && minor >= 19

if (!supported) {
  const why =
    major >= 24
      ? "Node >= 24 provides its own `localStorage` global that shadows jsdom's and is undefined " +
        'without --localstorage-file, so the jsdom test suites fail with confusing undefined errors.'
      : 'This project depends on packages that require Node >= 22.19.0.'

  process.stderr.write(
    `\nUnsupported Node version for the Omi Windows desktop test suite.\n\n` +
      `  required: ${RANGE}   (package.json "engines.node", and what CI pins)\n` +
      `  running:  v${process.versions.node}\n\n` +
      `${why}\n\n` +
      `Switch with your version manager, e.g. \`nvm use 22\` or \`fnm use 22\`, then re-run.\n\n`
  )
  process.exit(1)
}
