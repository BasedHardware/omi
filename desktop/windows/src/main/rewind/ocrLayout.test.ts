import { describe, it, expect } from 'vitest'
import {
  buildOcrContextText,
  clusterOcrRows,
  filterScreenChromeLines,
  parseStoredOcrLines,
  serializeOcrLayoutMarkdown,
  serializeOcrLinesForStorage
} from './ocrLayout'
import type { OcrLine } from '../../shared/types'

const line = (over: Partial<OcrLine>): OcrLine => ({
  text: 'text',
  x: 0,
  y: 0,
  w: 20,
  h: 10,
  confidence: 0.9,
  ...over
})

describe('ocrLayout', () => {
  it('clusters OCR lines into visual rows and orders each row left-to-right', () => {
    const rows = clusterOcrRows([
      line({ text: 'World', x: 35, y: 12 }),
      line({ text: 'Hello', x: 10, y: 10 }),
      line({ text: 'Second row', x: 10, y: 40, w: 80 })
    ])

    expect(rows).toHaveLength(2)
    expect(rows[0].text).toBe('Hello World')
    expect(rows[1].text).toBe('Second row')
  })

  it('splits visual rows when y coordinates differ by more than 10px', () => {
    const rows = clusterOcrRows([
      line({ text: 'First', x: 10, y: 100 }),
      line({ text: 'same row', x: 35, y: 110 }),
      line({ text: 'next row', x: 10, y: 111 })
    ])

    expect(rows).toHaveLength(2)
    expect(rows[0].text).toBe('First same row')
    expect(rows[1].text).toBe('next row')
  })

  it('filters likely menu and taskbar OCR before layout serialization', () => {
    expect(
      filterScreenChromeLines(
        [
          line({ text: 'File Edit View', y: 20 }),
          line({ text: 'Document content', y: 120 }),
          line({ text: 'Taskbar clock', y: 1050 })
        ],
        { width: 1920, height: 1080 }
      ).map((l) => l.text)
    ).toEqual(['Document content'])
  })

  it('serializes clustered rows as markdown with approximate screen positions', () => {
    expect(
      serializeOcrLayoutMarkdown(
        [line({ text: 'File', x: 10, y: 50 }), line({ text: 'Edit', x: 80, y: 50 })],
        { width: 200, height: 100 }
      )
    ).toBe('- top 50%, left 5%: File | Edit')
  })

  it('stores only valid OCR lines and tolerates bad stored JSON', () => {
    const stored = serializeOcrLinesForStorage([
      line({ text: 'Keep me', x: 1.4, y: 2.6 }),
      line({ text: 'Tiny but valid', x: 20, y: 20, w: 0.4, h: 0.4 }),
      line({ text: '   ' }),
      line({ text: 'bad size', w: 0 })
    ])

    expect(stored).not.toBeNull()
    expect(parseStoredOcrLines(stored)).toEqual([
      { text: 'Keep me', x: 1, y: 3, w: 20, h: 10, confidence: 0.9 },
      { text: 'Tiny but valid', x: 20, y: 20, w: 1, h: 1, confidence: 0.9 }
    ])
    expect(parseStoredOcrLines('{not json')).toEqual([])
  })

  it('falls back to plain OCR text when no stored layout is available', () => {
    expect(buildOcrContextText('plain text', null)).toBe('plain text')
  })

  it('builds layout-aware context when stored lines cover the OCR text', () => {
    const stored = serializeOcrLinesForStorage([
      line({ text: 'Visible', x: 10, y: 50, w: 50 }),
      line({ text: 'text', x: 70, y: 50, w: 40 })
    ])

    expect(
      buildOcrContextText('Visible\ntext', stored, {
        width: 200,
        height: 100
      })
    ).toBe('- top 50%, left 5%: Visible text')
  })

  it('builds layout-aware context without dropping the full OCR text', () => {
    const stored = serializeOcrLinesForStorage([
      line({ text: 'Visible', x: 10, y: 50, w: 50 }),
      line({ text: 'text', x: 70, y: 50, w: 40 })
    ])

    expect(
      buildOcrContextText('Visible text\nExtra uncaptured text', stored, {
        width: 200,
        height: 100
      })
    ).toBe(
      '- top 50%, left 5%: Visible text\n\nFull OCR text:\nVisible text\nExtra uncaptured text'
    )
  })
})
