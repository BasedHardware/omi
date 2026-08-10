import { notFound } from 'next/navigation';
import { CaseStatusView } from '@/components/fair-use/CaseStatusView';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.omi.me';

interface CaseStatus {
  case_ref: string;
  stage: 'none' | 'warning' | 'throttle' | 'restrict';
  message: string;
  created_at: string;
  updated_at: string;
}

async function getCaseStatus(ref: string): Promise<CaseStatus | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/v1/fair-use/case/${encodeURIComponent(ref)}/status`, {
      cache: 'no-store',
    });
    if (res.status === 404) return null;
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export default async function CaseStatusPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;

  // Validate format: FU- followed by hex chars
  if (!/^FU-[A-Fa-f0-9]{6,12}$/i.test(ref)) {
    notFound();
  }

  const status = await getCaseStatus(ref);

  return <CaseStatusView caseRef={ref} status={status} />;
}
