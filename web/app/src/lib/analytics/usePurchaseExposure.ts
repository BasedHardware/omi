import { useEffect, useRef } from 'react';
import { PurchaseObservation } from './purchaseContract.generated';
import { trackPurchaseEvent } from './subscriptionFunnel';

export function usePurchaseExposure(
  visible: boolean,
  source: string,
  currentPlan: string,
  surface: string,
  catalogTier = 'not_applicable',
) {
  const observation = useRef(new PurchaseObservation(trackPurchaseEvent));
  useEffect(() => {
    if (!visible) {
      observation.current = new PurchaseObservation(trackPurchaseEvent);
      return;
    }
    observation.current.view({
      source,
      current_plan: currentPlan,
      surface,
      catalog_tier: catalogTier,
    });
  }, [visible, source, currentPlan, surface, catalogTier]);
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
