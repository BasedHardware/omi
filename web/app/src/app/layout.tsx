import type { Metadata } from 'next';
import { AuthProvider } from '@/components/auth/AuthProvider';
import { MobileBlockOverlay } from '@/components/layout/MobileBlockOverlay';
import { BetaRibbon } from '@/components/ui/BetaRibbon';
import './globals.css';

export const metadata: Metadata = {
  title: 'Omi - Your AI Companion',
  description: 'Omi Web App - Access your conversations anywhere',
  icons: {
    icon: '/logo.png',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-bg-primary text-text-primary font-body antialiased">
        <MobileBlockOverlay />
        <BetaRibbon />
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
