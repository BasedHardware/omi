import { useState } from "react";
import { auth, googleProvider, db } from '@/lib/firebase';
import { signInWithPopup } from 'firebase/auth';
import { doc, getDoc, setDoc } from 'firebase/firestore';
import { toast } from "sonner";

interface LoginButtonProps {
  onLoadingChange?: (isLoading: boolean) => void;
}

export const LoginButton = ({ onLoadingChange }: LoginButtonProps) => {
  const [isLoading, setIsLoading] = useState(false);

  const handleGoogleSignIn = async () => {
    try {
      setIsLoading(true);
      if (onLoadingChange) onLoadingChange(true);
      
      const currentUser = auth.currentUser;
      const result = await signInWithPopup(auth, googleProvider);
      const user = result.user;
      
      if (currentUser && currentUser.isAnonymous && currentUser.uid !== user.uid) {
        try {
          await fetch('https://www.veyrax.com/api/integrations/omi/merge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
              old_uid: currentUser.uid, 
              new_uid: user.uid 
            })
          });
        } catch (error) {
          console.log('Falied to migrate')
        }
      }

      const userRef = doc(db, 'users', user.uid);
      const userSnap = await getDoc(userRef);

      if (!userSnap.exists()) {
        const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        await setDoc(userRef, {
          time_zone: timeZone,
          created_at: new Date(),
        });
      }
      
      toast.success('Signed in successfully');
    } catch (error: any) {
      toast.error('Failed to sign in with Google')
    } finally {
      setIsLoading(false);
      if (onLoadingChange) onLoadingChange(false);
    }
  };

  return (
    <span
      className="text-white hover:text-gray-200 cursor-pointer text-xs md:text-sm"
      onClick={handleGoogleSignIn}
    >
      {isLoading ? (
        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></div>
      ) : (
        "Sign In"
      )}
    </span>
  );
}; 
