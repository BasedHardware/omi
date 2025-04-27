import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Toaster } from 'sonner';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
});

export const metadata: Metadata = {
  title: "Omi by Based Hardware",
  description: "AI Twitter",
  icons: {
    icon: "/basedfavicon.png",
  },
  openGraph: {
    title: "Omi by Based Hardware",
    description: "AI Twitter",
    images: [
      {
        url: "/omidevice.webp",
        width: 1200,
        height: 630,
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Omi by Based Hardware",
    description: "AI Twitter",
    images: ["/omidevice.webp"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link rel="icon" href="/omifavicon.ico" />
      </head>
      <body className={`${inter.variable} font-sans antialiased`}>
        {children}
        <Toaster />
      </body>
    </html>
  );
}
