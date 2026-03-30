import { redirect } from 'next/navigation';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Nooto - Your AI Companion',
  description: 'Nooto - Your AI companion that turns thoughts into action. Access your conversations, memories, and AI-powered apps.',
  openGraph: {
    title: 'Nooto - Your AI Companion',
    description: 'Nooto - Your AI companion that turns thoughts into action. Access your conversations, memories, and AI-powered apps.',
    url: '/',
    type: 'website',
    images: [
      {
        url: '/login-bg.png',
        width: 1200,
        height: 630,
        alt: 'Nooto - Thought to Action',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Nooto - Your AI Companion',
    description: 'Nooto - Your AI companion that turns thoughts into action. Access your conversations, memories, and AI-powered apps.',
    images: ['/login-bg.png'],
  },
};

export default function HomePage() {
  // Redirect to the login page as the home page
  redirect('/login');
}
