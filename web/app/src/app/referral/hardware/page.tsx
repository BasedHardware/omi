'use client';

import { Suspense } from 'react';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';
import { HardwareReferralClient } from './HardwareReferralClient';

registerMoonshineRoute('/referral/hardware', HardwareReferralPage, 'root');

export default function HardwareReferralPage() {
  return (
    <Suspense>
      <HardwareReferralClient />
    </Suspense>
  );
}
