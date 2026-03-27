import type { Metadata } from 'next';
import { brand } from '@/lib/config';
import { FaqContent } from './faq-content';

export const metadata: Metadata = {
  title: `FAQ — ${brand.name}`,
  description: `Frequently asked questions about ${brand.name}, the AI-powered wearable companion.`,
};

export default function FaqPage() {
  return <FaqContent />;
}
