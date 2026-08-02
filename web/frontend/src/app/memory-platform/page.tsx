import type { Metadata } from 'next';
import PlatformPage from '@/src/components/memory-platform/platform-page';

export const metadata: Metadata = {
  title: 'Memory Platform',
  description: 'Omi memory for APIs, MCP, local replicas, and embedded products.',
};

export default function MemoryPlatformPage() {
  return <PlatformPage />;
}
