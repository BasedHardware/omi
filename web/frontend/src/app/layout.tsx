import type { Metadata } from 'next';
import { Mulish } from 'next/font/google';
import './globals.css';
import AppHeader from '../components/shared/app-header';
import ConditionalFooter from '../components/shared/conditional-footer';
import envConfig from '../constants/envConfig';
import { GleapInit } from '@/src/components/shared/gleap';
import { GoogleAnalytics } from '@/src/components/shared/google-analytics';

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
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <script src="https://elfsightcdn.com/platform.js" async></script>
      </head>
      <body className={inter.className}>
        <AppHeader />
        {/* Elfsight Announcement Bar */}
        <div className="elfsight-app-4df8bf4f-92a3-44bb-8bae-fcdac7faa58a" data-elfsight-app-lazy></div>
        <main className="flex min-h-screen flex-col">
          <div className="w-full flex-grow">{children}</div>
        </main>
        <ConditionalFooter />
      </body>
      <GleapInit />
      <GoogleAnalytics />
    </html>
  );
}
