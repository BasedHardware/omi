import type { Metadata } from 'next';
import { Mulish } from 'next/font/google';
import './globals.css';
import AppHeader from '../components/shared/app-header';
import Footer from '../components/shared/footer';
import envConfig from '../constants/envConfig';
import { GleapInit } from '@/src/components/shared/gleap';
import { AuthProvider } from '../context/AuthContext';

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
      <body className={inter.className}>
        <AuthProvider>
          <AppHeader />
          <main className="flex min-h-screen flex-col">
            <div className="w-full flex-grow">{children}</div>
          </main>
          <Footer />
          <GleapInit />
        </AuthProvider>
      </body>
    </html>
  );
}
