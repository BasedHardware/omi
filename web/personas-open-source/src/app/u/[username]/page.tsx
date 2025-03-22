'use client';

import { useRouter } from 'next/navigation';
import { collection, query, where, getDocs } from 'firebase/firestore';
import { db } from '@/lib/firebase';
import { Button } from '@/components/ui/button';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { use, useEffect, useState } from 'react';

type Props = {
  params: Promise<{ username: string }>
}

export default function UsernamePage({ params }: Props) {
  const { username } = use(params);
  const router = useRouter();
  const [error, setError] = useState<'not_found' | 'private' | null>(null);
  
  useEffect(() => {
    const fetchBotByUsername = async () => {
      try {
        const q = query(
          collection(db, 'plugins_data'),
          where('username', '==', username.toLowerCase())
        );
        const querySnapshot = await getDocs(q);

        if (!querySnapshot.empty) {
          const botDoc = querySnapshot.docs[0];
          const botData = botDoc.data();
          
          if (botData.private) {
            setError('private');
          } else {
            router.replace(`/chat?id=${botDoc.id}`);
          }
        } else {
          setError('not_found');
        }
      } catch (e) {
        console.error('Error fetching bot:', e);
        setError('not_found');
      }
    };

    fetchBotByUsername();
  }, [username, router]);

  if (!error) {
    return null;
  }

  return (
    <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center p-4">
      <div className="absolute top-4 left-4">
        <Link href="/">
          <Button variant="ghost" size="icon" className="text-white hover:text-gray-300">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
      </div>

      <div className="text-center max-w-md mx-auto">
        <h1 className="text-6xl font-serif mb-8 text-white">omi</h1>
        {error === 'not_found' ? (
          <>
            <p className="text-gray-400 mb-4">This persona does not exist</p>
            <p className="text-sm text-gray-500">The persona you're looking for could not be found.</p>
          </>
        ) : (
          <>
            <p className="text-gray-400 mb-4">This persona is private</p>
            <p className="text-sm text-gray-500">You don't have access to view this persona.</p>
          </>
        )}
        <Link href="/">
          <Button 
            className="mt-8 w-full max-w-sm rounded-full bg-white text-black hover:bg-gray-200"
          >
            Return Home
          </Button>
        </Link>
      </div>
    </div>
  );
}