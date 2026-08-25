import type { Metadata } from 'next';
import { LoginClient } from './LoginClient';

export const metadata: Metadata = {
  title: 'Sign In to Omi',
  description: 'Sign in to Omi - Your AI companion that turns thoughts into action. Access your conversations, memories, and AI-powered apps.',
  alternates: {
    canonical: '/login',
  },
  openGraph: {
    title: 'Sign In to Omi',
    description: 'Sign in to Omi - Your AI companion that turns thoughts into action. Access your conversations, memories, and AI-powered apps.',
    url: '/login',
    type: 'website',
    images: [
      {
        url: '/login-bg.png',
        width: 1200,
        height: 630,
        alt: 'Omi - Thought to Action',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Sign In to Omi',
    description: 'Sign in to Omi - Your AI companion that turns thoughts into action. Access your conversations, memories, and AI-powered apps.',
    images: ['/login-bg.png'],
  },
};

export default function LoginPage() {
  return <LoginClient />;
}
