// @vitest-environment jsdom
// What actually reaches the DOM. The grammar is covered in lib/markdown; this
// asserts the things only a render can show: that a table is a real table, that
// a refused link is not an anchor, and that nothing here can inject HTML.
import { describe, expect, it, afterEach } from 'vitest'
import { render, cleanup, screen } from '@testing-library/react'
import { Markdown } from './Markdown'

afterEach(cleanup)

function html(text: string): string {
  return render(<Markdown text={text} />).container.innerHTML
}

describe('tables', () => {
  const TABLE = '| Name | Size |\n| :--- | ---: |\n| alpha | 1 |\n| beta | 2 |'

  it('renders a real table, not a paragraph of pipes', () => {
    render(<Markdown text={TABLE} />)
    expect(screen.getByRole('table')).toBeTruthy()
    expect(screen.getAllByRole('columnheader').map((c) => c.textContent)).toEqual(['Name', 'Size'])
    expect(screen.getAllByRole('row')).toHaveLength(3)
  })

  it('applies each column’s alignment', () => {
    render(<Markdown text={TABLE} />)
    const [left, right] = screen.getAllByRole('columnheader')
    expect(left.className).toContain('text-left')
    expect(right.className).toContain('text-right')
  })

  it('scrolls the table rather than the page', () => {
    // A wide table must not widen the chat column.
    render(<Markdown text={TABLE} />)
    const region = screen.getByRole('region', { name: 'Scrollable table' })
    expect(region.className).toContain('overflow-x-auto')
  })

  it('renders inline markdown inside cells', () => {
    render(<Markdown text={'| a | b |\n| --- | --- |\n| **bold** | `code` |'} />)
    expect(screen.getByText('bold').tagName).toBe('STRONG')
    expect(screen.getByText('code').tagName).toBe('CODE')
  })
})

describe('blocks', () => {
  it('renders headings at their level', () => {
    render(<Markdown text={'# One\n\n### Three'} />)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('One')
    expect(screen.getByRole('heading', { level: 3 }).textContent).toBe('Three')
  })

  it('renders a blockquote', () => {
    expect(html('> quoted')).toContain('<blockquote')
  })

  it('renders a thematic break', () => {
    expect(html('a\n\n---\n\nb')).toContain('<hr')
  })

  it('renders nested lists as nested lists', () => {
    const { container } = render(<Markdown text={'- outer\n  - inner'} />)
    expect(container.querySelectorAll('ul ul')).toHaveLength(1)
  })

  it('renders a task item as a read-only checkbox', () => {
    render(<Markdown text={'- [ ] todo\n- [x] done'} />)
    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[]
    expect(boxes.map((b) => b.checked)).toEqual([false, true])
    // A rendered reply is a transcript; the box reports, it does not edit.
    expect(boxes.every((b) => b.readOnly)).toBe(true)
  })

  it('starts an ordered list at the number given', () => {
    const { container } = render(<Markdown text={'3. a\n4. b'} />)
    expect(container.querySelector('ol')?.getAttribute('start')).toBe('3')
  })
})

describe('links', () => {
  it('renders an allowed link as an anchor that opens externally', () => {
    render(<Markdown text={'[docs](https://omi.me)'} />)
    const link = screen.getByRole('link', { name: 'docs' })
    expect(link.getAttribute('href')).toBe('https://omi.me')
    expect(link.getAttribute('rel')).toBe('noreferrer')
  })

  it('renders a refused link as text with no anchor at all', () => {
    // The label still shows; only the navigation is withheld.
    render(<Markdown text={'[click me](javascript:alert(1))'} />)
    expect(screen.queryByRole('link')).toBeNull()
    expect(screen.getByText('click me')).toBeTruthy()
  })

  it('never emits a javascript href even inside other formatting', () => {
    const rendered = html('**bold [x](javascript:alert(1)) tail**')
    expect(rendered).not.toContain('javascript:')
    expect(rendered).toContain('<strong>')
  })

  it('keeps a bolded link clickable', () => {
    // The measured defect: this used to render the raw markdown characters.
    render(<Markdown text={'**see [docs](https://omi.me) now**'} />)
    expect(screen.getByRole('link', { name: 'docs' })).toBeTruthy()
    expect(html('**see [docs](https://omi.me) now**')).not.toContain('](')
  })
})

describe('nothing here can inject HTML', () => {
  it('renders raw tags as text', () => {
    const rendered = html('<script>alert(1)</script> and <img src=x onerror=alert(1)>')
    expect(rendered).not.toContain('<script')
    expect(rendered).not.toContain('<img')
    expect(rendered).toContain('&lt;script&gt;')
  })

  it('renders a markdown image as its alt text and requests nothing', () => {
    const rendered = html('![a diagram](https://tracker.example/p.png)')
    expect(rendered).not.toContain('<img')
    expect(rendered).not.toContain('tracker.example')
    expect(rendered).toContain('a diagram')
  })

  it('renders HTML inside a code block as text', () => {
    const rendered = html('```\n<script>alert(1)</script>\n```')
    expect(rendered).not.toContain('<script')
    expect(rendered).toContain('&lt;script&gt;')
  })
})

describe('streaming', () => {
  it('renders every prefix of a reply without throwing', () => {
    // The renderer runs on every token, so each prefix must render.
    const doc =
      '# Title\n\nSome *text*.\n\n| a | b |\n| --- | --: |\n| 1 | 2 |\n\n' +
      '> quoted\n\n- [ ] task\n  - deep\n\n---\n\n```ts\nconst x = 1\n```\nEnd.'
    for (let n = 0; n <= doc.length; n++) {
      expect(() => {
        render(<Markdown text={doc.slice(0, n)} />)
        cleanup()
      }).not.toThrow()
    }
  })

  it('keeps a half-typed marker literal', () => {
    expect(html('a **b')).toContain('a **b')
  })
})
