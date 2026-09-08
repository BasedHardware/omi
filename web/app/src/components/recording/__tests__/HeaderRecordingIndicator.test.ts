import { describe, expect, it } from 'vitest';
import {
  getRecordControlRightOffset,
  RECORD_CONTROL_EDGE_OFFSET,
} from '@/lib/desktopChrome';

describe('desktop Record control placement', () => {
  it('keeps a full pane inset from the top-right edge', () => {
    expect(RECORD_CONTROL_EDGE_OFFSET).toBe(24);
    expect(getRecordControlRightOffset(false, false)).toBe(24);
  });

  it('preserves the inset as side panels open', () => {
    expect(getRecordControlRightOffset(true, false)).toBe(428);
    expect(getRecordControlRightOffset(false, true)).toBe(428);
    expect(getRecordControlRightOffset(true, true)).toBe(832);
  });
});
