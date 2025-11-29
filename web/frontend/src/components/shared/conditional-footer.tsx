'use client';

import { usePathname } from 'next/navigation';
import Footer from './footer';

export default function ConditionalFooter() {
  const pathname = usePathname();
  const isConversationPage = pathname?.includes('/conversations');

  if (isConversationPage) {
    return null;
  }

  return <Footer />;
}

