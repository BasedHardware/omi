import type { Metadata } from 'next';
import { Mulish } from 'next/font/google';
import './globals.css';

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
      <body className={inter.className}>{children}</body>
    </html>
  );
}
