import { PostHogManager } from '@/lib/analytics/posthog';

/**
 * Client presentation gates for the ladder-v1 plans sheet. Backend visibility
 * and entitlement decisions win. Lifecycle: rollout; owner: dazheng;
 * review-by: 2026-11-13; default off. Mirrors mobile `PlanStorefrontGate`.
 */
export class PlanStorefrontGate {
  static readonly enabledFlag = 'web-plan-storefront';

  static sheetEnabled(
    read = PostHogManager.isFeatureEnabled.bind(PostHogManager),
  ): Promise<boolean> {
    return read(PlanStorefrontGate.enabledFlag).catch(() => false);
  }

  /** Contextual entry points need both their own flag and the sheet flag. */
  static async contextualEnabled(
    read = PostHogManager.isFeatureEnabled.bind(PostHogManager),
  ): Promise<boolean> {
    const flags = await Promise.all([
      PlanStorefrontGate.sheetEnabled(read),
      read(ContextualUpsellsGate.enabledFlag).catch(() => false),
    ]);
    return flags.every(Boolean);
  }
}

/** Independent rollout key for the budget meter, nudge and exhausted entry. */
class ContextualUpsellsGate {
  static readonly enabledFlag = 'web-contextual-upsells';
}
