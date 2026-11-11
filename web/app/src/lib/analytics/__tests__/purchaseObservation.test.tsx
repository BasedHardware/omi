import { render, cleanup } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
const sink = vi.hoisted(() => vi.fn());
vi.mock('../subscriptionFunnel', () => ({ trackPurchaseEvent: sink }));
import { useAllowanceObservation } from '../usePurchaseExposure';
import { purchaseContract, purchasePayload } from '../purchaseContract.generated';
afterEach(() => {
  cleanup();
  sink.mockClear();
});
function Block({ reached, shown }: { reached: boolean; shown: boolean }) {
  useAllowanceObservation(reached, 'usage_budget', 'chat', 'budget_exhausted', shown);
  return shown ? <div>Server cap</div> : null;
}
it('server reach and committed block UI are independent and deduplicated', () => {
  const tree = render(<Block reached shown={false} />);
  expect(sink.mock.calls.map(([id]) => id)).toEqual(['allowanceReached']);
  tree.rerender(<Block reached shown={false} />);
  expect(sink).toHaveBeenCalledTimes(1);
  tree.rerender(<Block reached shown />);
  tree.rerender(<Block reached shown />);
  expect(sink.mock.calls.map(([id]) => id)).toEqual([
    'allowanceReached',
    'allowanceBlockShown',
  ]);
  tree.rerender(<Block reached={false} shown={false} />);
  tree.rerender(<Block reached shown />);
  expect(sink.mock.calls.map(([id]) => id)).toEqual([
    'allowanceReached',
    'allowanceBlockShown',
    'allowanceReached',
    'allowanceBlockShown',
  ]);
});
it('every event projects only closed contract properties', () => {
  for (const id of Object.keys(purchaseContract) as (keyof typeof purchaseContract)[]) {
    const payload = purchasePayload(id, {
      source: 'private',
      plan: 'private',
      uid: 'private',
      url: 'private',
      error: 'private',
    });
    expect(JSON.stringify(payload)).not.toContain('private');
    for (const [key, value] of Object.entries(payload.properties))
      expect(
        (purchaseContract[id].properties as Record<string, readonly string[]>)[key],
      ).toContain(value);
  }
});
