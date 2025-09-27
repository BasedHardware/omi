import type { Metadata } from 'next';
import { Mulish } from 'next/font/google';
import './globals.css';
import AppHeader from '../components/shared/app-header';
import Footer from '../components/shared/footer';
import envConfig from '../constants/envConfig';
import { GleapInit } from '@/src/components/shared/gleap';
import { GoogleAnalytics } from '@/src/components/shared/google-analytics';
import MobileAppBanner from '@/src/components/shared/mobile-app-banner';

const inter = Mulish({
  subsets: ['latin'],
  weight: ['200', '400', '500', '600', '700'],
  style: ['italic', 'normal'],
});

export const metadata: Metadata = {
  title: {
    default: 'Omi',
    template: '%s | Omi',
  },
  metadataBase: new URL(envConfig.WEB_URL),
  description: 'Open-source AI wearable Build using the power of recall',
  other: {
    'apple-itunes-app': 'app-id=6502156163',
    'google-play-app': 'app-id=com.friend.ios',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <AppHeader />
        <MobileAppBanner />
        <main className="flex min-h-screen flex-col">
          <div className="w-full flex-grow">{children}</div>
        </main>
        <Footer />
      </body>
      <GleapInit />
      <GoogleAnalytics />
    </html>
  );
}
