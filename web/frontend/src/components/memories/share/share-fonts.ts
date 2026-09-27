import { DM_Sans, Plus_Jakarta_Sans } from 'next/font/google';

// The web app's type pair (web/app/tailwind.config.ts), exposed as CSS
// variables that share-note.css reads.
const display = Plus_Jakarta_Sans({
  subsets: ['latin'],
  weight: ['600', '700'],
  variable: '--sn-font-display',
  display: 'swap',
});

const body = DM_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--sn-font-body',
  display: 'swap',
});

export const shareFonts = `${display.variable} ${body.variable}`;
