'use client';

import { useEffect, useState } from 'react';
import { useParams } from '@tschk/moonshine-next/navigation';
import { CaseStatusView } from '@/components/fair-use/CaseStatusView';
import { registerMoonshineRoute } from '@/moonshine/register-client-route';

// This page runs entirely in the browser, on the web origin. The backend
// allows no cross-origin callers by default (`CORS_ALLOWED_ORIGINS` is empty in
// `backend/main.py`), so the status read goes through the same-origin public
// passthrough rather than straight at the API.
const PUBLIC_API_BASE_URL = '/api/proxy/public';

interface CaseStatus {
  case_ref: string;
  stage: 'none' | 'warning' | 'throttle' | 'restrict';
  message: string;
  created_at: string;
  updated_at: string;
}

async function getCaseStatus(ref: string): Promise<CaseStatus | null> {
  try {
    const res = await fetch(
      `${PUBLIC_API_BASE_URL}/v1/fair-use/case/${encodeURIComponent(ref)}/status`,
      {
        cache: 'no-store',
      },
    );
    if (res.status === 404) return null;
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export default function CaseStatusPage() {
  const params = useParams();
  const ref = params.ref ?? '';
  const [status, setStatus] = useState<CaseStatus | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!/^FU-[A-Fa-f0-9]{6,12}$/i.test(ref)) {
      setLoaded(true);
      return;
    }
    let active = true;
    getCaseStatus(ref).then((nextStatus) => {
      if (!active) return;
      setStatus(nextStatus);
      setLoaded(true);
    });
    return () => {
      active = false;
    };
  }, [ref]);

  // Validate format: FU- followed by hex chars
  if (!/^FU-[A-Fa-f0-9]{6,12}$/i.test(ref)) {
    return <CaseStatusView caseRef={ref} status={null} />;
  }

  if (!loaded) return <div className="min-h-screen bg-bg-primary" />;

  return <CaseStatusView caseRef={ref} status={status} />;
}

registerMoonshineRoute('/case/:ref', CaseStatusPage, 'root');
