import { useEffect, useState } from 'react';

import { omiFlagEnabled } from '@/lib/omiFlags';

/**
 * Kill switch for the web/macOS cancel-flow parity work (SCA-2171).
 *
 * Web reads the Omi flag store key below; macOS reads the same key through
 * `PostHogManager.shared.isFeatureEnabled`. An unlisted key, a failed read or
 * no answer before the timeout keeps today's plain confirm path, which is the
 * required default until David's render/copy approval is recorded and the
 * release owner turns it on (`CANCEL_FLOW_PARITY_ENABLED`).
 *
 * The flag only gates the added steps. It never gates the cancel entry point:
 * with the flag off, cancelling still works exactly as it does today.
 */
export const CANCEL_FLOW_PARITY_FLAG = 'cancel_flow_parity';

export function useCancelFlowParityEnabled(): boolean {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    let active = true;
    omiFlagEnabled(CANCEL_FLOW_PARITY_FLAG)
      .then((value) => {
        if (active) setEnabled(value === true);
      })
      .catch(() => {
        if (active) setEnabled(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return enabled;
}
