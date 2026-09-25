import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  renderSummarySections,
  selectConversationSummary,
  type SummarySelectionInput,
} from '@/lib/conversationSummarySelection';

interface SummaryContract {
  cases: Array<{
    id: string;
    conversation: SummarySelectionInput;
    expected: {
      kind: 'app' | 'overview' | 'sections' | 'empty';
      content: string;
      app_id: string | null;
      result_index: number | null;
    };
  }>;
}

function contract(): SummaryContract {
  const path = resolve(process.cwd(), '../../contracts/parity/conversation_summary.json');
  return JSON.parse(readFileSync(path, 'utf8')) as SummaryContract;
}

describe('conversation summary selection contract', () => {
  for (const testCase of contract().cases) {
    it(testCase.id, () => {
      const selected = selectConversationSummary(testCase.conversation);
      expect(selected).toEqual({
        content: testCase.expected.content,
        kind: testCase.expected.kind,
        appId: testCase.expected.app_id,
        resultIndex: testCase.expected.result_index,
      });
    });
  }

  it('ignores heading-only sections in the projection', () => {
    expect(renderSummarySections([{ heading: 'Unused', body_markdown: ' ' }])).toBe('');
  });
});
