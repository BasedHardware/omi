import { redirect } from 'next/navigation';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Omi - Your AI Companion',
  description: 'Omi - Your AI companion that turns thoughts into action. Access your conversations, memories, and AI-powered apps.',
  openGraph: {
    title: 'Omi - Your AI Companion',
    description: 'Omi - Your AI companion that turns thoughts into action. Access your conversations, memories, and AI-powered apps.',
    url: '/',
    type: 'website',
    images: [
      {
        url: 'https://www.omi.me/cdn/shop/files/gempages_515188559477474548-60e6e62e-9101-4826-84bc-04a22a88619a.png?v=18356679557113353564',
        width: 1200,
        height: 630,
        alt: 'Omi - Thought to Action',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Omi - Your AI Companion',
    description: 'Omi - Your AI companion that turns thoughts into action. Access your conversations, memories, and AI-powered apps.',
    images: ['https://www.omi.me/cdn/shop/files/gempages_515188559477474548-60e6e62e-9101-4826-84bc-04a22a88619a.png?v=18356679557113353564'],
  },
};

export default function HomePage() {
  // Redirect to the login page as the home page
  redirect('/login');
}
