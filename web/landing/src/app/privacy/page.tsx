import { Metadata } from 'next';
import { brand } from '@/lib/config';
import { PrivacyContent } from './privacy-content';

export const metadata: Metadata = {
  title: `Privacy Policy — ${brand.name}`,
  description: `At ${brand.name}, your privacy and the security of your data are our top priorities.`,
};

export default function PrivacyPage() {
  return <PrivacyContent />;
}
