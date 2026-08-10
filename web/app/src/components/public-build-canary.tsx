'use client';

import { useEffect, useState } from 'react';
import { auth } from '@/lib/firebase';

const inputs = [
  process.env.NEXT_PUBLIC_API_BASE_URL,
  process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  process.env.NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID,
  process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY,
];

export function PublicBuildCanary() {
  const [status, setStatus] = useState('pending');

  useEffect(() => {
    setStatus(
      inputs.every((value) => typeof value === 'string' && value.trim()) &&
        auth.app.options.apiKey
        ? 'ready'
        : 'missing',
    );
  }, []);

  return (
    <span aria-hidden="true" data-omi-public-build-canary={`app:${status}`} hidden />
  );
}
