import type { Metadata } from 'next';
import MemoryWidget from '../components/memory-widget';
import { buildPlatformMetadata } from '../utils/metadata';

export async function generateMetadata(): Promise<Metadata> {
  return buildPlatformMetadata({
    title: 'Omi memory widget',
    description: 'The embeddable Omi memory surface.',
    path: '/memory-platform/widget',
    noIndex: true,
  });
}

interface WidgetPageProps {
  searchParams: Promise<{ demo?: string }>;
}

/**
 * Framed surface. It is pinned over the viewport so the marketing chrome from
 * the root layout never appears inside a host product's iframe.
 */
export default async function MemoryWidgetPage({ searchParams }: WidgetPageProps) {
  const params = await searchParams;
  return (
    <div className="fixed inset-0 z-50 bg-[#0a0a0a]">
      <MemoryWidget demo={params?.demo === '1'} />
    </div>
  );
}
