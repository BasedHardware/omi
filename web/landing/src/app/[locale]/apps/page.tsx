import type { Metadata } from 'next';
import { AppsContent } from './apps-content';

export const metadata: Metadata = {
  title: 'Nooto App Store',
  description: 'Explore thousands of apps for productivity, integrations, health, education, and more.',
};

export default function AppsPage() {
  return <AppsContent />;
}
