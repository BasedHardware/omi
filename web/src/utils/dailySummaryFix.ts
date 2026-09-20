/**
 * OMI Web App - Daily Summary Delivery Preference Safeguard
 * Issue #15245: Prevent delivery time reset on daily summary toggle
 * Author: Hasnain Chavhan (@HasnainChavhan)
 */

export interface DailySummaryConfig {
  enabled: boolean;
  deliveryTime: string; // HH:mm format
}

export function toggleDailySummarySafely(
  currentConfig: DailySummaryConfig,
  newEnabledState: boolean
): DailySummaryConfig {
  return {
    enabled: newEnabledState,
    // Preserve existing deliveryTime preference instead of resetting to default
    deliveryTime: currentConfig.deliveryTime || "20:00"
  };
}
