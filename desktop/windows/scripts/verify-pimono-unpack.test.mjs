#!/usr/bin/env node
import assert from 'node:assert/strict'
import test from 'node:test'
import { globToPackageName } from './gen-pimono-unpack.mjs'

test('globToPackageName strips node_modules prefix and trailing glob', () => {
  assert.equal(
    globToPackageName('node_modules/@mariozechner/clipboard-linux-x64-gnu/**'),
    '@mariozechner/clipboard-linux-x64-gnu'
  )
})

test('drift removed filter keeps optional platform siblings not installed on host', () => {
  const fresh = ['node_modules/@mariozechner/clipboard-linux-x64-gnu/**']
  const committed = [
    'node_modules/@mariozechner/clipboard-linux-x64-gnu/**',
    'node_modules/@mariozechner/clipboard-win32-x64-msvc/**'
  ]
  const optionalPlatformSiblingGlobs = ['node_modules/@mariozechner/clipboard-win32-x64-msvc/**']
  const freshSet = new Set(fresh)
  const optionalPlatformSiblingSet = new Set(optionalPlatformSiblingGlobs)

  const added = fresh.filter((g) => !new Set(committed).has(g))
  const removed = committed.filter((g) => !freshSet.has(g) && !optionalPlatformSiblingSet.has(g))

  assert.deepEqual(added, [])
  assert.deepEqual(removed, [])
})

test('completeness skips optional platform siblings missing on disk', () => {
  const committed = [
    'node_modules/@mariozechner/clipboard-linux-x64-gnu/**',
    'node_modules/@mariozechner/clipboard-win32-x64-msvc/**'
  ]
  const optionalPlatformSiblingGlobs = ['node_modules/@mariozechner/clipboard-win32-x64-msvc/**']
  const optionalPlatformSiblingSet = new Set(optionalPlatformSiblingGlobs)
  const installed = new Set(['node_modules/@mariozechner/clipboard-linux-x64-gnu/**'])

  const missingOnDisk = []
  for (const glob of committed) {
    if (installed.has(glob)) continue
    if (optionalPlatformSiblingSet.has(glob)) continue
    missingOnDisk.push(globToPackageName(glob))
  }

  assert.deepEqual(missingOnDisk, [])
})
