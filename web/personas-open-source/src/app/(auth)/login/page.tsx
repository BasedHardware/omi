'use client';

import { Button } from '@/components/ui/button';
import { ArrowLeft } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { auth, googleProvider, db } from '@/lib/firebase';
import { signInWithPopup } from 'firebase/auth';
import { doc, getDoc, setDoc } from 'firebase/firestore';

export default function SignInPage() {
  const router = useRouter();

  const handleGoogleSignIn = async () => {
    try {
      const result = await signInWithPopup(auth, googleProvider);
      const user = result.user;

      const userRef = doc(db, 'users', user.uid);
      const userSnap = await getDoc(userRef);

      if (!userSnap.exists()) {
        const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        await setDoc(userRef, {
          time_zone: timeZone,
          created_at: new Date(),
        });
      }

      router.back();
    } catch (error) {
      console.error('Error signing in or saving user data:', error);
    }
  };

  return (
    <div className="min-h-screen bg-black text-white">
      {/* Back Button */}
      <div className="absolute left-4 top-4">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => router.back()}
          className="text-white hover:text-gray-300"
        >
          <ArrowLeft className="h-5 w-5" />
        </Button>
      </div>

      {/* Main Content */}
      <div className="flex min-h-screen flex-col items-center justify-center px-4">
        {/* Logo/Text */}
        <div className="mb-12 text-center">
          <h1 className="mb-8 font-serif text-6xl text-white">omi</h1>
          <p className="text-gray-400">Improve yourself with your new AI mentor</p>
        </div>

        {/* Continue Button */}
        <Button
          className="flex w-full max-w-sm items-center justify-center gap-2 rounded-full bg-white text-black hover:bg-gray-200"
          onClick={handleGoogleSignIn}
        >
          Continue with Google
        </Button>

        {/* Footer */}
        <div className="fixed bottom-4 mx-auto w-full max-w-4xl px-4">
          <div className="flex justify-between text-xs text-gray-500">
            <span>Omi Chat © 2025</span>
            <div className="flex gap-4">
              <Button
                variant="link"
                className="h-auto p-0 text-xs text-gray-500 hover:text-white"
              >
                Terms & Conditions
              </Button>
              <Button
                variant="link"
                className="h-auto p-0 text-xs text-gray-500 hover:text-white"
              >
                Privacy Policy
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
