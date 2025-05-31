'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/src/context/AuthContext';

export default function LoginPage() {
  const { user, signInWithGoogle, signInWithApple, loading } = useAuth();
  const router = useRouter();

  React.useEffect(() => {
    if (user && !loading) {
      router.push('/');
    }
  }, [user, loading, router]);

  return (
    <div className="min-h-screen bg-gray-900 px-4 py-20 text-white">
      <div className="mx-auto max-w-md rounded-lg bg-gray-800 p-8 shadow-lg">
        <h1 className="mb-6 text-center text-3xl font-bold">Sign In</h1>
        <p className="mb-8 text-center text-gray-300">
          Sign in to create and manage your Omi apps
        </p>

        <div className="space-y-4">
          <button
            onClick={signInWithGoogle}
            className="flex w-full items-center justify-center gap-3 rounded-md bg-white px-4 py-3 text-gray-800 transition hover:bg-gray-100"
            disabled={loading}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              width="24"
              height="24"
            >
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            Continue with Google
          </button>

          <button
            onClick={signInWithApple}
            className="flex w-full items-center justify-center gap-3 rounded-md border border-gray-700 bg-black px-4 py-3 text-white transition hover:bg-gray-900"
            disabled={loading}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              width="24"
              height="24"
              fill="white"
            >
              <path d="M16.125 0.1875C14.598 0.344531 12.8438 1.28906 11.8594 2.57812C10.9688 3.73438 10.2656 5.4375 10.5 7.09375C12.1406 7.14844 13.7812 6.17969 14.7188 4.89062C15.6094 3.65625 16.2656 1.98438 16.125 0.1875ZM16.9219 7.42969C14.7188 7.42969 13.8281 8.83594 12.3281 8.83594C10.8281 8.83594 9.28125 7.48438 7.40625 7.48438C5.25 7.48438 2.90625 9.32812 2.90625 12.9844C2.90625 18 6.9375 23.8125 9.3281 23.8125C10.7344 23.8125 11.5781 22.8281 13.3594 22.8281C15.1875 22.8281 15.75 23.8125 17.3438 23.8125C18.9844 23.8125 20.2969 21.5156 21.0938 19.8906C21.7031 18.6562 21.9375 18.0469 22.4062 16.6406C18.4219 15.1875 17.9062 9.60938 21.9844 7.875C20.5781 7.42969 18.6094 7.42969 16.9219 7.42969Z" />
            </svg>
            Continue with Apple
          </button>
        </div>
      </div>
    </div>
  );
}
