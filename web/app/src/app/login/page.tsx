'use client';

import { Suspense } from 'react';
import { LoginClient } from './LoginClient';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

registerMoonshineRoute('/login', LoginPage, 'root');

export default function LoginPage() {
  return (
    <Suspense>
      <LoginClient />
    </Suspense>
  );
}
