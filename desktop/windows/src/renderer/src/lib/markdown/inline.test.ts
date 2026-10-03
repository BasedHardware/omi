// Inline parsing. Several cases here are regressions against measured
// behaviour of the renderer this replaces, not hypotheticals: the shipped
// build was run against each input and the result recorded before the rewrite.
import { describe, expect, it } from 'vitest'
import { isSafeHref, parseInline, plainText, type InlineNode } from './inline'

/** Compact shape for assertions: `strong(text)`, `code`, `link(href|text)`. */
function shape(nodes: InlineNode[]): string {
  return nodes
    .map((n) => {
      switch (n.kind) {
        case 'text':
          return n.value
        case 'code':
          return `code(${n.value})`
        case 'link':
          return `link(${n.href}|${shape(n.children)})`
        case 'deadLink':
          return `dead(${shape(n.children)})`
        default:
          return `${n.kind}(${shape(n.children)})`
      }
    })
    .join('')
}

describe('emphasis', () => {
  it('reads bold, italic and strikethrough', () => {
    expect(shape(parseInline('a **b** c'))).toBe('a strong(b) c')
    expect(shape(parseInline('a *b* c'))).toBe('a em(b) c')
    expect(shape(parseInline('a _b_ c'))).toBe('a em(b) c')
    expect(shape(parseInline('a __b__ c'))).toBe('a strong(b) c')
    // Strikethrough rendered as literal tildes before this change.
    expect(shape(parseInline('a ~~b~~ c'))).toBe('a del(b) c')
  })

  it('nests', () => {
    // The measured defect: `**see [docs](https://x.com) now**` came out as
    // bold text containing the literal characters of the link.
    expect(shape(parseInline('**see [docs](https://x.com) now**'))).toBe(
      'strong(see link(https://x.com|docs) now)'
    )
    expect(shape(parseInline('**bold with `code` inside**'))).toBe(
      'strong(bold with code(code) inside)'
    )
    expect(shape(parseInline('*italic with **bold** inside*'))).toBe(
      'em(italic with strong(bold) inside)'
    )
  })

  it('prefers bold over two italics', () => {
    expect(shape(parseInline('**x**'))).toBe('strong(x)')
  })

  it('leaves an unclosed run literal', () => {
    // A reply is streamed, so half-typed markers are the normal state.
    expect(shape(parseInline('a **b'))).toBe('a **b')
    expect(shape(parseInline('a ~~b'))).toBe('a ~~b')
  })

  it('does not emphasise inside a word with underscores', () => {
    // `my_var_name` is an identifier, not an italic. Asterisks keep working
    // intraword because that is what CommonMark says.
    expect(shape(parseInline('call my_var_name here'))).toBe('call my_var_name here')
    expect(shape(parseInline('a*b*c'))).toBe('aem(b)c')
  })

  it('does not let an underscore OPEN inside a word', () => {
    // Separate from the case above, which the closing rule alone already
    // handles. Here the closer is legal (followed by a space) and only the
    // opening rule stops `my_var_` from italicising `var`.
    expect(shape(parseInline('my_var_ end'))).toBe('my_var_ end')
  })

  it('is not fooled by an empty run', () => {
    expect(shape(parseInline('****'))).toBe('****')
    expect(shape(parseInline('a ** ** b'))).toBe('a ** ** b')
  })
})

describe('code spans', () => {
  it('takes their content literally', () => {
    expect(shape(parseInline('use `**not bold**` here'))).toBe('use code(**not bold**) here')
  })

  it('supports multi-backtick fences and strips one padding space', () => {
    expect(shape(parseInline('`` ` ``'))).toBe('code(`)')
  })

  it('leaves an unterminated backtick literal', () => {
    expect(shape(parseInline('a `b'))).toBe('a `b')
  })

  it('does not let a delimiter inside code close an outer run', () => {
    expect(shape(parseInline('**a `b** c` d**'))).toBe('strong(a code(b** c) d)')
  })
})

describe('escapes', () => {
  it('renders an escaped marker literally and does not emphasise', () => {
    // Measured before the rewrite: this produced `a \` + <em>not italic\</em>
    // + ` b`. Both the backslash showed AND it italicised.
    expect(shape(parseInline('a \\*not italic\\* b'))).toBe('a *not italic* b')
  })

  it('escapes the other markers too', () => {
    expect(shape(parseInline('\\`not code\\`'))).toBe('`not code`')
    expect(shape(parseInline('\\[not a link\\]'))).toBe('[not a link]')
    expect(shape(parseInline('a \\\\ b'))).toBe('a \\ b')
  })

  it('leaves a backslash before an ordinary character alone', () => {
    expect(shape(parseInline('C:\\Users\\dog'))).toBe('C:\\Users\\dog')
  })
})

describe('links', () => {
  it('reads a labelled link', () => {
    expect(shape(parseInline('[docs](https://omi.me)'))).toBe('link(https://omi.me|docs)')
  })

  it('parses the label, so a link can hold emphasis', () => {
    expect(shape(parseInline('[**bold** label](https://omi.me)'))).toBe(
      'link(https://omi.me|strong(bold) label)'
    )
  })

  it('flattens a link inside a link label', () => {
    // Links cannot nest; the inner one becomes its own text.
    expect(shape(parseInline('[a [b](https://b.com) c](https://a.com)'))).toBe(
      'link(https://a.com|a b c)'
    )
  })

  it('links a bare URL', () => {
    expect(shape(parseInline('see https://omi.me for more'))).toBe(
      'see link(https://omi.me|https://omi.me) for more'
    )
  })

  it('leaves sentence punctuation outside a bare URL', () => {
    expect(shape(parseInline('see https://omi.me.'))).toBe(
      'see link(https://omi.me|https://omi.me).'
    )
  })

  it('does not autolink inside a word', () => {
    expect(shape(parseInline('xhttps://omi.me'))).toBe('xhttps://omi.me')
  })
})

describe('which hrefs may become live links', () => {
  // The security rule. Chat replies can be steered by indirect prompt
  // injection because the prompt includes OCR of the user's screen, so the
  // model can be induced to emit any href it likes.
  it('allows only http, https and mailto', () => {
    expect(isSafeHref('https://omi.me')).toBe(true)
    expect(isSafeHref('http://omi.me')).toBe(true)
    expect(isSafeHref('mailto:a@b.com')).toBe(true)
  })

  it.each([
    ['javascript', 'javascript:alert(1)'],
    ['data', 'data:text/html,<script>alert(1)</script>'],
    ['file', 'file:///C:/Windows/System32/'],
    ['UNC path', '\\\\attacker\\share\\payload'],
    ['custom protocol', 'ms-word:ofe|u|https://x'],
    ['relative', '/etc/passwd'],
    ['empty', '']
  ])('refuses %s', (_label, href) => {
    expect(isSafeHref(href)).toBe(false)
  })

  it('refuses a scheme split by a control character', () => {
    // URL parsers strip these before reading the scheme, so this reaches the
    // browser as `javascript:` while sailing past a plain prefix test.
    expect(isSafeHref('java\tscript:alert(1)')).toBe(false)
    expect(isSafeHref('java\nscript:alert(1)')).toBe(false)
    expect(isSafeHref('\u0000javascript:alert(1)')).toBe(false)
  })

  it('refuses a control character hiding the real host', () => {
    // The case that gives the control-character rule its own weight: the
    // scheme here IS https, so the allowlist passes it. A URL parser strips
    // the tab, leaving `https://omi.me@evil.example`, where everything before
    // the `@` is userinfo and the site actually visited is evil.example. The
    // href a user sees in a tooltip and the host they reach disagree.
    expect(isSafeHref('https://omi.me\t@evil.example')).toBe(false)
    expect(isSafeHref('https://omi.me\n@evil.example')).toBe(false)
  })

  it('keeps the label of a refused link but marks it dead', () => {
    // The user still reads what the model wrote; it just is not clickable.
    expect(shape(parseInline('[click me](javascript:alert(1))'))).toBe('dead(click me)')
  })

  it('never autolinks a bare non-http scheme', () => {
    expect(shape(parseInline('run file:///C:/Windows now'))).toBe('run file:///C:/Windows now')
  })

  it('does not autolink a URL carrying a control character', () => {
    // The autolink pattern excludes whitespace but not other control
    // characters, so this is where the href check earns its place on that path
    // rather than duplicating the pattern: without it the link would carry a
    // control character straight into an href.
    expect(shape(parseInline('see https://omi.me\u0001@evil.example now'))).toBe(
      'see https://omi.me\u0001@evil.example now'
    )
  })
})

describe('images', () => {
  it('renders an image as its alt text and fetches nothing', () => {
    // Deliberate, not unimplemented: a reply can be steered by what is on the
    // user's screen, so a rendered remote image is a tracking pixel that fires
    // on load with nothing clicked.
    expect(shape(parseInline('![a diagram](https://x.com/p.png)'))).toBe('a diagram')
  })

  it('drops an image with a refused URL the same way', () => {
    expect(shape(parseInline('![x](javascript:alert(1))'))).toBe('x')
  })

  it('keeps a bare exclamation mark', () => {
    expect(shape(parseInline('wow! [docs](https://x.com)'))).toBe('wow! link(https://x.com|docs)')
  })
})

describe('plain text', () => {
  it('flattens a tree to what the reader sees', () => {
    expect(plainText(parseInline('**a** `b` [c](https://c.com)'))).toBe('a b c')
  })
})
