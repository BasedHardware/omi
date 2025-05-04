import { Button } from "@/components/ui/button";
import { 
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription
} from "@/components/ui/dialog";
import { auth, googleProvider, db } from '@/lib/firebase';
import { signInWithPopup, linkWithPopup, AuthErrorCodes, fetchSignInMethodsForEmail, getAdditionalUserInfo, GoogleAuthProvider } from 'firebase/auth';
import { doc, getDoc, setDoc } from 'firebase/firestore';
import { useState } from "react";
import { toast } from "sonner";

interface LoginDialogProps {
  showLoginDialog: boolean;
  setShowLoginDialog: (show: boolean) => void;
  onAuthSuccess: (userId: string) => void;
}

export const LoginDialog: React.FC<LoginDialogProps> = ({ 
  showLoginDialog, 
  setShowLoginDialog, 
  onAuthSuccess 
}) => {
  const [isLoading, setIsLoading] = useState(false);

  const handleGoogleSignIn = async () => {
    try {
      setIsLoading(true);
      
      const currentUser = auth.currentUser;
      const result = await signInWithPopup(auth, googleProvider);
      const credential = GoogleAuthProvider.credentialFromResult(result);
      const user = result.user;
      
      if (currentUser && currentUser.isAnonymous && currentUser.uid !== user.uid) {
        try {
          const migrateResponse = await fetch('https://veyrax.com/api/integrations/omi/merge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
              old_uid: currentUser.uid, 
              new_uid: user.uid 
            })
          });
          
          if (migrateResponse.ok) {
            console.log('Data migration initiated successfully');
          } else {
            console.error('Failed to initiate data migration:', await migrateResponse.text());
          }
        } catch (migrateError) {
          console.error('Error calling migration API:', migrateError);
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

      onAuthSuccess(user.uid);
    } catch (error: any) {
      console.error("Sign in error:", error);
      toast.error('Failed to sign in. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={showLoginDialog} onOpenChange={setShowLoginDialog}>
      <DialogContent 
        className="bg-black border-0 p-6 sm:max-w-lg" 
        closeButtonClassName="text-white"
      >
        <DialogTitle className="sr-only">Sign In to omi</DialogTitle>
        <div className="flex flex-col items-center justify-center min-h-[350px]">
          <div className="text-center mb-10">
            <img src="/omilogo.png" alt="Omi Logo" className="h-12 mb-4 mx-auto" />
            <div className="text-gray-400 mb-2">Sign in to continue</div>
            <div className="text-sm text-gray-500 mb-8">Create a free account to use all features</div>
          </div>

          <Button
            className="w-full max-w-sm py-6 flex items-center justify-center gap-3 rounded-full bg-white text-black hover:bg-gray-200 transition-colors"
            onClick={handleGoogleSignIn}
            disabled={isLoading}
          >
            {isLoading ? (
              <div className="w-5 h-5 border-2 border-black border-t-transparent rounded-full animate-spin"></div>
            ) : (
              <>
                <svg width="20" height="20" viewBox="0 0 256 262" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid">
                  <path d="M255.878 133.451c0-10.734-.871-18.567-2.756-26.69H130.55v48.448h71.947c-1.45 12.04-9.283 30.172-26.69 42.356l-.244 1.622 38.755 30.023 2.685.268c24.659-22.774 38.875-56.282 38.875-96.027" fill="#4285F4"/>
                  <path d="M130.55 261.1c35.248 0 64.839-11.605 86.453-31.622l-41.196-31.913c-11.024 7.688-25.82 13.055-45.257 13.055-34.523 0-63.824-22.773-74.269-54.25l-1.531.13-40.298 31.187-.527 1.465C35.393 231.798 79.49 261.1 130.55 261.1" fill="#34A853"/>
                  <path d="M56.281 156.37c-2.756-8.123-4.351-16.827-4.351-25.82 0-8.994 1.595-17.697 4.206-25.82l-.073-1.73L15.26 71.312l-1.335.635C5.077 89.644 0 109.517 0 130.55s5.077 40.905 13.925 58.602l42.356-32.782" fill="#FBBC05"/>
                  <path d="M130.55 50.479c24.514 0 41.05 10.589 50.479 19.438l36.844-35.974C195.245 12.91 165.798 0 130.55 0 79.49 0 35.393 29.301 13.925 71.947l42.211 32.783c10.59-31.477 39.891-54.251 74.414-54.251" fill="#EB4335"/>
                </svg>
                Continue with Google
              </>
            )}
          </Button>
          
          <div className="mt-8 text-xs text-gray-500">
            By continuing, you agree to our <a href="#" className="underline hover:text-white">Terms of Service</a> and <a href="#" className="underline hover:text-white">Privacy Policy</a>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}; 