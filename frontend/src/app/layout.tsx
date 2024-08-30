import type { Metadata } from 'next';
import { Mulish } from 'next/font/google';
import './globals.css';
import AppHeader from '../components/shared/app-header';

const inter = Mulish({
  subsets: ['latin'],
  weight: ['200', '400', '500', '600', '700'],
  style: ['italic', 'normal'],
});

export const metadata: Metadata = {
  title: {
    default: 'Based Hardware',
    template: '%s | Based Hardware',
  },
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
        <AppHeader />
        <main className="flex min-h-screen flex-col">
          <div className="w-full flex-grow">{children}</div>
        </main>
        {/* <Footer /> */}
      </body>
    </html>
  );
}
