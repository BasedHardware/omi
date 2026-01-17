/**
 * Feature flags for controlling feature availability.
 *
 * RECORDING_ENABLED: Set to true when WebSocket auth backend is deployed.
 *
 * Backend PR: https://github.com/BasedHardware/omi/pull/4141
 *
 * To enable recording:
 * 1. Ensure the backend WebSocket auth PR is merged and deployed
 * 2. Change RECORDING_ENABLED to true
 * 3. The "Coming Soon" badges will automatically disappear
 */
export const RECORDING_ENABLED = false;
