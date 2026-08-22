// Block grammar. The cases marked "measured" record what the shipped renderer
// did with the same input before this change.
import { describe, expect, it } from 'vitest'
import { isThematicBreak, parseBlocks, type Block, type ListBlock } from './blocks'

const kinds = (blocks: Block[]): string[] => blocks.map((b) => b.kind)

function firstList(blocks: Block[]): ListBlock {
  const list = blocks.find((b) => b.kind === 'list')
  if (!list) throw new Error('no list block')
  return list as ListBlock
}

describe('paragraphs and headings', () => {
  it('splits paragraphs on blank lines', () => {
    expect(kinds(parseBlocks('one\n\ntwo'))).toEqual(['paragraph', 'paragraph'])
  })

  it('keeps a heading’s level', () => {
    // Measured: every level rendered as the same bold paragraph, so `#` and
    // `######` were indistinguishable.
    const blocks = parseBlocks('# One\n\n###### Six')
    expect(blocks).toEqual([
      { kind: 'heading', level: 1, text: 'One' },
      { kind: 'heading', level: 6, text: 'Six' }
    ])
  })

  it('does not treat a bare # as a heading', () => {
    expect(kinds(parseBlocks('#hashtag'))).toEqual(['paragraph'])
  })

  it('ends a paragraph at a heading with no blank line', () => {
    expect(kinds(parseBlocks('text\n## Heading'))).toEqual(['paragraph', 'heading'])
  })
})

describe('thematic breaks', () => {
  it('recognises the three markers', () => {
    expect(isThematicBreak('---')).toBe(true)
    expect(isThematicBreak('***')).toBe(true)
    expect(isThematicBreak('___')).toBe(true)
    expect(isThematicBreak('- - -')).toBe(true)
  })

  it('needs three of the same marker', () => {
    expect(isThematicBreak('--')).toBe(false)
    expect(isThematicBreak('-*-')).toBe(false)
    expect(isThematicBreak('')).toBe(false)
  })

  it('breaks the paragraph above it', () => {
    // Measured: `Before\n---\nAfter` was one paragraph with the dashes inside
    // it, because there was no thematic-break rule at all.
    expect(kinds(parseBlocks('Before\n---\nAfter'))).toEqual([
      'paragraph',
      'thematicBreak',
      'paragraph'
    ])
  })

  it('stays literal inside a code block', () => {
    // Code is scanned first, which is what protects it.
    const blocks = parseBlocks('```\n---\n```')
    expect(kinds(blocks)).toEqual(['code'])
    expect(blocks[0]).toMatchObject({ text: '---' })
  })
})

describe('code blocks', () => {
  it('keeps the language tag', () => {
    expect(parseBlocks('```ts\nconst a = 1\n```')).toEqual([
      { kind: 'code', language: 'ts', text: 'const a = 1' }
    ])
  })

  it('has no language when none is given', () => {
    expect(parseBlocks('```\nplain\n```')[0]).toMatchObject({ language: null })
  })

  it('keeps an unclosed fence as code while a reply streams', () => {
    // Deliberate divergence from macOS, which keeps it as text. A half-arrived
    // fence is the normal state mid-stream, and watching the block form reads
    // better than watching raw markdown reflow when the closer lands.
    const blocks = parseBlocks('```py\nx = 1\ny = 2')
    expect(kinds(blocks)).toEqual(['code'])
    expect(blocks[0]).toMatchObject({ text: 'x = 1\ny = 2' })
  })
})

describe('blockquotes', () => {
  it('reads a quote', () => {
    // Measured: rendered as literal `&gt; quoted line` text.
    const blocks = parseBlocks('> quoted line\n> second line')
    expect(kinds(blocks)).toEqual(['quote'])
    expect((blocks[0] as { blocks: Block[] }).blocks).toEqual([
      { kind: 'paragraph', text: 'quoted line\nsecond line' }
    ])
  })

  it('parses the quote’s contents, so it can hold a list', () => {
    const blocks = parseBlocks('> - a\n> - b')
    const inner = (blocks[0] as { blocks: Block[] }).blocks
    expect(kinds(inner)).toEqual(['list'])
  })

  it('handles a quote marker with no space', () => {
    expect(kinds(parseBlocks('>tight'))).toEqual(['quote'])
  })
})

describe('lists', () => {
  it('reads a flat bullet list', () => {
    const list = firstList(parseBlocks('- a\n- b'))
    expect(list.ordered).toBe(false)
    expect(list.items.map((i) => i.text)).toEqual(['a', 'b'])
  })

  it('keeps the number an ordered list starts at', () => {
    const list = firstList(parseBlocks('3. a\n4. b'))
    expect(list.ordered).toBe(true)
    expect(list.start).toBe(3)
  })

  it('keeps nesting', () => {
    // Measured: `- outer / - inner / - inner2 / - outer2` rendered as ONE flat
    // list of four items. The structure the model expressed was discarded.
    const list = firstList(parseBlocks('- outer\n  - inner\n  - inner2\n- outer2'))
    expect(list.items.map((i) => i.text)).toEqual(['outer', 'outer2'])
    expect(list.items[0].children?.items.map((i) => i.text)).toEqual(['inner', 'inner2'])
    expect(list.items[1].children).toBeNull()
  })

  it('nests more than one level deep', () => {
    const list = firstList(parseBlocks('- a\n  - b\n    - c'))
    expect(list.items[0].children?.items[0].children?.items[0].text).toBe('c')
  })

  it('nests a numbered list inside a bullet', () => {
    const list = firstList(parseBlocks('- a\n  1. one\n  2. two'))
    expect(list.items[0].children?.ordered).toBe(true)
  })

  it('starts a new list when the marker type changes', () => {
    expect(kinds(parseBlocks('1. a\n- b'))).toEqual(['list', 'list'])
  })

  it('reads task items', () => {
    // Measured: rendered as literal `[ ] buy milk` and `[x] done`.
    // The sample avoids the bare word the deferred-work-marker check scans
    // for; it read this line's task text as an un-tracked marker and failed
    // the PR (run 32117987727).
    const list = firstList(parseBlocks('- [ ] buy milk\n- [x] done\n- plain'))
    expect(list.items.map((i) => i.checked)).toEqual([false, true, null])
    expect(list.items.map((i) => i.text)).toEqual(['buy milk', 'done', 'plain'])
  })

  it('accepts an uppercase X', () => {
    expect(firstList(parseBlocks('- [X] done')).items[0].checked).toBe(true)
  })

  it('ends at a blank line', () => {
    expect(kinds(parseBlocks('- a\n- b\n\nAfter.'))).toEqual(['list', 'paragraph'])
  })
})

describe('tables in a document', () => {
  it('becomes its own block', () => {
    // Measured: the whole thing was one paragraph of literal pipes.
    const blocks = parseBlocks('Intro.\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\nAfter.')
    expect(kinds(blocks)).toEqual(['paragraph', 'table', 'paragraph'])
  })

  it('ends the paragraph directly above it', () => {
    expect(kinds(parseBlocks('Intro.\n| a | b |\n| --- | --- |\n| 1 | 2 |'))).toEqual([
      'paragraph',
      'table'
    ])
  })

  it('stays literal inside a code block', () => {
    expect(kinds(parseBlocks('```\n| a | b |\n| --- | --- |\n```'))).toEqual(['code'])
  })
})

describe('robustness', () => {
  it('returns nothing for empty input', () => {
    expect(parseBlocks('')).toEqual([])
    expect(parseBlocks('   \n\n  ')).toEqual([])
  })

  it('normalises CRLF out of the text, not just the block shape', () => {
    // Asserting only the block kinds passed even with normalisation removed,
    // because a lone `\r` line still trims to empty and still splits the
    // paragraphs. The carriage returns survived INSIDE the text, where they
    // reach the DOM.
    expect(kinds(parseBlocks('a\r\n\r\nb'))).toEqual(['paragraph', 'paragraph'])
    expect(parseBlocks('a\r\nb')).toEqual([{ kind: 'paragraph', text: 'a\nb' }])
    expect(parseBlocks('# Title\r\n')).toEqual([{ kind: 'heading', level: 1, text: 'Title' }])
  })

  it('terminates on every prefix of a document', () => {
    // A reply is rendered on every token, so the parser runs against every
    // prefix of the final text. Any one of them looping would hang the app.
    const doc =
      '# Title\n\nIntro *text* with `code`.\n\n| a | b |\n| --- | --: |\n| 1 | 2 |\n\n' +
      '> quoted\n> - nested item\n\n- [ ] task\n  - deep\n\n---\n\n```ts\nconst x = 1\n```\nEnd.'
    for (let n = 0; n <= doc.length; n++) {
      expect(() => parseBlocks(doc.slice(0, n))).not.toThrow()
    }
  })
})
