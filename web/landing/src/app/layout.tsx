import type { ReactNode } from 'react';

// Root layout passes through to [locale]/layout.tsx which handles <html> and <body>.
// This pattern is required by next-intl with App Router.
// See: https://next-intl.dev/docs/getting-started/app-router/with-i18n-routing

type Props = {
  children: ReactNode;
};

export default function RootLayout({ children }: Props) {
  return children;
}
