import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'
import { describe, expect, it } from 'vitest'
import { OP_OCR, OP_WINDOW, encodeRequest } from './helperProtocol'

const helper = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../../../resources/linux-ocr-helper/omi-ocr-helper'
)

function requestHelper(opcode: number, payload: Buffer): Promise<Record<string, unknown>> {
  return new Promise((resolveResponse, reject) => {
    const child = spawn(process.execPath, [helper], { stdio: ['pipe', 'pipe', 'pipe'] })
    const stdout: Buffer[] = []
    const stderr: Buffer[] = []
    child.stdout.on('data', (chunk: Buffer) => stdout.push(chunk))
    child.stderr.on('data', (chunk: Buffer) => stderr.push(chunk))
    child.once('error', reject)
    child.once('close', (code) => {
      if (code !== 0)
        return reject(new Error(`helper exited ${code}: ${Buffer.concat(stderr).toString('utf8')}`))
      const frame = Buffer.concat(stdout)
      const length = frame.readUInt32LE(0)
      if (length !== frame.length - 4) return reject(new Error('helper returned an invalid frame'))
      resolveResponse(JSON.parse(frame.subarray(4).toString('utf8')) as Record<string, unknown>)
    })
    child.stdin.end(encodeRequest(opcode, payload))
  })
}

describe.skipIf(process.platform !== 'linux')('linux OCR helper', () => {
  it('returns a window response over the helper protocol', async () => {
    const response = await requestHelper(OP_WINDOW, Buffer.alloc(0))
    expect(response).toMatchObject({
      app: expect.any(String),
      title: expect.any(String),
      pid: expect.any(Number),
      processName: expect.any(String)
    })
  })

  it('runs Tesseract through the helper when an OCR fixture is supplied', async () => {
    const fixture = process.env.OMI_HELPER_OCR_FIXTURE
    if (!fixture) return
    const response = await requestHelper(OP_OCR, await readFile(fixture))
    expect(response.ok).toBe(true)
    expect(response.fullText).toContain(process.env.OMI_HELPER_EXPECT_TEXT)
  })
})
