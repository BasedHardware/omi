import type { Metadata } from 'next';
import { AuthProvider } from '@/components/auth/AuthProvider';
import { MobileBlockOverlay } from '@/components/layout/MobileBlockOverlay';
import { RecordingProvider, RecordingController } from '@/components/recording';
import { ToastProvider } from '@/components/ui/Toast';
import './globals.css';

export const metadata: Metadata = {
  metadataBase: new URL('https://omi.me'),
  title: {
    default: 'Omi - Your AI Companion',
    template: '%s | Omi',
  },
  description: 'Omi Web App - Access your conversations anywhere',
  icons: {
    icon: [
      { url: '/favicon.png', sizes: '32x32', type: 'image/png' },
      { url: '/logo.png', sizes: '192x192', type: 'image/png' },
      { url: '/logo.png', sizes: '512x512', type: 'image/png' },
    ],
    shortcut: ['/favicon.png'],
    apple: [
      { url: '/logo.png', sizes: '180x180', type: 'image/png' },
    ],
    other: [
      {
        rel: 'apple-touch-icon-precomposed',
        url: '/logo.png',
      },
    ],
  },
  openGraph: {
    siteName: 'Omi',
    locale: 'en_US',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    site: '@omiHQ',
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
        <AuthProvider>
          <RecordingProvider>
            <ToastProvider>
              <RecordingController />
              {children}
            </ToastProvider>
          </RecordingProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
