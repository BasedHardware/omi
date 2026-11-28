import { useCallback, useEffect, useRef } from 'react';
import { PurchaseObservation } from './purchaseContract.generated';
import { trackPurchaseEvent } from './subscriptionFunnel';

export function usePurchaseExposure(
  visible: boolean,
  source: string,
  currentPlan: string,
  surface: string,
  catalogTier = 'not_applicable',
  presentationActive = true,
) {
  const observation = useRef(new PurchaseObservation(trackPurchaseEvent));
  // Deferred renderers call this only after selectable options commit. The
  // observation stays with the host while loading temporarily unmounts a list.
  const record = useCallback(() => {
    observation.current.view({
      source,
      current_plan: currentPlan,
      surface,
      catalog_tier: catalogTier,
    });
  }, [source, currentPlan, surface, catalogTier]);
  useEffect(() => {
    if (!presentationActive) {
      observation.current = new PurchaseObservation(trackPurchaseEvent);
      return;
    }
    if (!visible) return;
    record();
  }, [visible, presentationActive, record]);
  return record;
}

export function useAllowanceObservation(
  reached: boolean,
  kind: string,
  surface: string,
  reason: string,
  blockShown = false,
) {
  const observation = useRef(new PurchaseObservation(trackPurchaseEvent));
  useEffect(() => {
    const raw = { allowance_kind: kind, surface, reason };
    observation.current.allowance(reached, raw);
    observation.current.allowance(blockShown, raw, true);
  }, [reached, kind, surface, reason, blockShown]);
}
