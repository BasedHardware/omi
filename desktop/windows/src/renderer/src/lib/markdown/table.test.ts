// GFM tables. Measured against the shipped renderer, a table came out as one
// paragraph of literal pipe characters, so every rule here is new behaviour.
import { describe, expect, it } from 'vitest'
import { parseAlignment, parseTable, splitCells } from './table'

const lines = (text: string): string[] => text.split('\n')

describe('splitting a row into cells', () => {
  it('handles the leading and trailing pipes', () => {
    expect(splitCells('| a | b | c |')).toEqual(['a', 'b', 'c'])
    expect(splitCells('a | b | c')).toEqual(['a', 'b', 'c'])
  })

  it('trims each cell', () => {
    expect(splitCells('|   a   |  b |')).toEqual(['a', 'b'])
  })

  it('keeps an escaped pipe as content', () => {
    // Without this a cell can never contain a pipe, which bites the moment the
    // model tabulates shell syntax or a regex alternation.
    expect(splitCells('| a \\| b | c |')).toEqual(['a | b', 'c'])
  })

  it('keeps a trailing escaped pipe as content', () => {
    expect(splitCells('| a | b \\|')).toEqual(['a', 'b |'])
  })

  it('ignores a pipe inside an inline code span', () => {
    expect(splitCells('| `a | b` | c |')).toEqual(['`a | b`', 'c'])
  })

  it('produces an empty cell rather than dropping it', () => {
    expect(splitCells('| a |  | c |')).toEqual(['a', '', 'c'])
  })
})

describe('separator alignment', () => {
  it('reads all four forms', () => {
    expect(parseAlignment('---')).toBe('left')
    expect(parseAlignment(':---')).toBe('left')
    expect(parseAlignment(':---:')).toBe('center')
    expect(parseAlignment('---:')).toBe('right')
  })

  it('needs at least three dashes', () => {
    // The floor is what stops an ordinary `| -- |` row from turning the line
    // above it into a table header.
    expect(parseAlignment('--')).toBeNull()
    expect(parseAlignment(':-:')).toBeNull()
  })

  it('rejects anything that is not dashes', () => {
    expect(parseAlignment('-a-')).toBeNull()
    expect(parseAlignment('')).toBeNull()
    expect(parseAlignment('===')).toBeNull()
  })
})

describe('reading a table', () => {
  it('reads header, alignments and rows', () => {
    const parsed = parseTable(lines('| Name | Size |\n| --- | ---: |\n| a | 1 |\n| b | 2 |'), 0)
    expect(parsed).not.toBeNull()
    expect(parsed!.table.header).toEqual(['Name', 'Size'])
    expect(parsed!.table.alignments).toEqual(['left', 'right'])
    expect(parsed!.table.rows).toEqual([
      ['a', '1'],
      ['b', '2']
    ])
    expect(parsed!.nextIndex).toBe(4)
  })

  it('stops at a blank line so prose can follow immediately', () => {
    const parsed = parseTable(lines('| a | b |\n| --- | --- |\n| 1 | 2 |\n\nAfter.'), 0)
    expect(parsed!.table.rows).toEqual([['1', '2']])
    expect(parsed!.nextIndex).toBe(3)
  })

  it('pads a short row and truncates a long one', () => {
    const parsed = parseTable(
      lines('| a | b | c |\n| --- | --- | --- |\n| 1 | 2 |\n| 1 | 2 | 3 | 4 |'),
      0
    )
    expect(parsed!.table.rows).toEqual([
      ['1', '2', ''],
      ['1', '2', '3']
    ])
  })

  it('ends the table at a row with fewer than two cells', () => {
    // macOS' rule: a one-cell line is prose, not a row, so the table ends and
    // the line goes back to the block scanner as ordinary text.
    const parsed = parseTable(lines('| a | b |\n| --- | --- |\n| 1 | 2 |\n| trailing'), 0)
    expect(parsed!.table.rows).toEqual([['1', '2']])
    expect(parsed!.nextIndex).toBe(3)
  })

  it('accepts a table with no body rows', () => {
    const parsed = parseTable(lines('| a | b |\n| --- | --- |'), 0)
    expect(parsed!.table.rows).toEqual([])
  })
})

describe('what is not a table', () => {
  it('needs a separator line', () => {
    expect(parseTable(lines('| a | b |\n| 1 | 2 |'), 0)).toBeNull()
  })

  it('needs the separator to match the header width', () => {
    expect(parseTable(lines('| a | b | c |\n| --- | --- |'), 0)).toBeNull()
  })

  it('needs every separator cell to be an alignment', () => {
    expect(parseTable(lines('| a | b |\n| --- | xx |'), 0)).toBeNull()
  })

  it('needs at least two columns', () => {
    // A one-column "table" is indistinguishable from prose with a stray pipe.
    expect(parseTable(lines('| a |\n| --- |'), 0)).toBeNull()
  })

  it('leaves ordinary prose containing a pipe alone', () => {
    expect(parseTable(lines('use a | b to pipe\nand then continue'), 0)).toBeNull()
  })

  it('needs a line after the header', () => {
    expect(parseTable(lines('| a | b |'), 0)).toBeNull()
  })
})
