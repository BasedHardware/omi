import type { Metadata } from 'next';
import { Mulish } from 'next/font/google';
import './globals.css';
import AppHeader from '../components/shared/app-header';
import ConditionalFooter from '../components/shared/conditional-footer';
import AnnouncementBar from '../components/shared/announcement-bar';
import envConfig from '../constants/envConfig';
import { GoogleAnalytics } from '@/src/components/shared/google-analytics';
import { PublicBuildCanary } from '../components/public-build-canary';

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
        <PublicBuildCanary />
        <AppHeader />
        {/* Elfsight Announcement Bar */}
        <AnnouncementBar />
        <main className="flex min-h-screen flex-col">
          <div className="w-full flex-grow">{children}</div>
        </main>
        <ConditionalFooter />
      </body>
      <GoogleAnalytics />
    </html>
  );
}
