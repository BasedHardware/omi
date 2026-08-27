import { describe, expect, it } from 'vitest';
import { parseStreamLine } from '../model';

describe('parseStreamLine', () => {
  it('parses think and data prefixes', () => {
    expect(parseStreamLine('think: hello')).toEqual({ type: 'think', text: 'hello' });
    expect(parseStreamLine('data: world')).toEqual({ type: 'data', text: 'world' });
  });

  it('returns null for a blank line', () => {
    expect(parseStreamLine('')).toBeNull();
    expect(parseStreamLine('   ')).toBeNull();
  });
});
