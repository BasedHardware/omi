// Root layout — next-intl handles locale routing via [locale]/layout.tsx
// This file is required by Next.js but delegates to the locale layout.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
