import type { Metadata, Viewport } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'PAPER — your day, printed',
  description:
    'A daily paper built from what you actually lived, not from topics you picked. One page, once a day, then it ends.',
  openGraph: {
    title: 'PAPER — your day, printed',
    description: 'Every news app reads what you click. This one reads what you lived.',
    type: 'website',
  },
};

export const viewport: Viewport = {
  themeColor: '#fffaf1',
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
