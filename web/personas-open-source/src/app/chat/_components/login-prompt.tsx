'use client';

import { Button } from "@/components/ui/button";
import { auth, db, googleProvider } from '@/lib/firebase';
import { signInWithPopup } from 'firebase/auth';
import { doc, getDoc, setDoc, collection, addDoc } from 'firebase/firestore';
import { Message } from '@/types/chat';

interface LoginPromptProps {
  messages: Message[];
  botName: string;
  botImage: string;
  botId: string;
  onLoginSuccess: () => void;
}

export function LoginPrompt({
  messages,
  botName,
  botImage,
  botId,
  onLoginSuccess
}: LoginPromptProps) {
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

      const createdPersonas = JSON.parse(localStorage.getItem('createdPersonas') || '[]');
      for (const personaId of createdPersonas) {
        try {
          const personaRef = doc(db, 'plugins_data', personaId);
          const personaSnap = await getDoc(personaRef);
          
          if (personaSnap.exists() && !personaSnap.data().uid) {
            await setDoc(personaRef, { uid: user.uid }, { merge: true });
          }
        } catch (error) {
          console.error(`Error updating persona ${personaId}:`, error);
        }
      }
      
      localStorage.removeItem('createdPersonas');

      if (messages.length > 0) {
        const userMessagesRef = collection(db, 'users', user.uid, 'messages');
        await addDoc(userMessagesRef, {
          messages,
          timestamp: new Date(),
          botName,
          botImage,
          lastMessage: messages[messages.length - 1]?.text || '',
          messageCount: messages.length,
          pluginId: botId
        });
      }

      onLoginSuccess();
    } catch (error) {
      console.error('Error signing in or saving user data:', error);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/90 flex items-center justify-center p-4 z-50">
      <div className="w-full max-w-lg">
        <div className="flex flex-col items-center justify-center min-h-[400px] px-4">
          <div className="text-center mb-12">
            <h1 className="text-6xl font-serif mb-8 text-white">omi</h1>
            <p className="text-gray-400 mb-4">Sign in to continue chatting</p>
            <p className="text-sm text-gray-500">Create a free account to unlock unlimited conversations</p>
          </div>
          <Button
            className="w-full max-w-sm flex items-center justify-center gap-2 rounded-full bg-white text-black hover:bg-gray-200"
            onClick={handleGoogleSignIn}
          >
            Continue with Google
          </Button>
        </div>
      </div>
    </div>
  );
}