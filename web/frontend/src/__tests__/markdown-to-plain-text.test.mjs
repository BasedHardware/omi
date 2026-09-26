import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { markdownToPlainText } from '../lib/markdown-to-plain-text.mjs';

describe('markdownToPlainText', () => {
  it('returns an empty string for undefined, null, and blank input', () => {
    assert.equal(markdownToPlainText(undefined), '');
    assert.equal(markdownToPlainText(null), '');
    assert.equal(markdownToPlainText(''), '');
    assert.equal(markdownToPlainText('   \n\t  '), '');
  });

  it('drops heading markers', () => {
    assert.equal(markdownToPlainText('## Riddle Answers'), 'Riddle Answers');
    assert.equal(markdownToPlainText('# Title\n### Nested'), 'Title Nested');
  });

  it('drops bold and italics markers', () => {
    assert.equal(markdownToPlainText('**Yes**: a fact'), 'Yes: a fact');
    assert.equal(markdownToPlainText('*italic* and __bold__'), 'italic and bold');
    assert.equal(markdownToPlainText('keep snake_case names'), 'keep snake_case names');
  });

  it('keeps link text and drops the URL', () => {
    assert.equal(
      markdownToPlainText('See [the docs](https://example.com/path) please'),
      'See the docs please',
    );
  });

  it('flattens nested lists into a single line', () => {
    const markdown = `## Riddle Answers
- Keyboard: keys without locks
  - nested detail
    1. numbered
- Venus: day lasts longer`;
    assert.equal(
      markdownToPlainText(markdown),
      'Riddle Answers Keyboard: keys without locks nested detail numbered Venus: day lasts longer',
    );
  });

  it('drops code fences and inline backticks, keeping the inner text', () => {
    const markdown = 'Use `npm test` then\n```js\nconst x = 1;\n```\ndone';
    assert.equal(markdownToPlainText(markdown), 'Use npm test then const x = 1; done');
  });

  it('collapses whitespace to single spaces', () => {
    assert.equal(markdownToPlainText('hello\n\n\t  world'), 'hello world');
  });

  it('truncates to about 200 characters at a word boundary with an ellipsis', () => {
    const words = Array.from({ length: 50 }, (_, i) => `word${i}`).join(' ');
    const result = markdownToPlainText(words);
    assert.ok(result.endsWith('...'));
    assert.ok(!result.includes('word49'));
    const withoutEllipsis = result.slice(0, -3);
    assert.ok(withoutEllipsis.length <= 200);
    assert.ok(!withoutEllipsis.endsWith(' '));
    assert.match(withoutEllipsis, /^word0(?: word\d+)*$/);
  });

  it('does not truncate short input', () => {
    assert.equal(markdownToPlainText('Short overview.'), 'Short overview.');
  });

  it('strips HTML tags and blockquote markers', () => {
    assert.equal(markdownToPlainText('> quoted <b>bold</b> text'), 'quoted bold text');
  });
});
