import type { Metadata } from 'next';
import { brand } from '@/lib/config';
import { DownloadContent } from './download-content';

export const metadata: Metadata = {
  title: `Download — ${brand.name}`,
  description: `Download ${brand.name} for iOS, Android, Mac, and Web. Available everywhere you work.`,
};

export default function DownloadPage() {
  return <DownloadContent />;
}
