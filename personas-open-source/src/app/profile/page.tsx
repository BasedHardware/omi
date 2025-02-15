'use client';

import { useEffect, useState } from 'react';
import { auth } from '@/lib/firebase';
import { useRouter } from 'next/navigation';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { updateProfile } from 'firebase/auth';
import { toast } from 'sonner';

const ProfilePage = () => {
  const router = useRouter();
  const [user, setUser] = useState<any>(null);
  const [displayName, setDisplayName] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unsubscribe = auth.onAuthStateChanged((user) => {
      setUser(user);
      setDisplayName(user?.displayName || '');
      setLoading(false);
    });

    return () => unsubscribe();
  }, []);

  if (loading) {
    return <div className="min-h-screen bg-black text-white flex items-center justify-center">Loading...</div>;
  }

  if (!user) {
    router.push('/'); // Redirect to homepage if not logged in
    return null;
  }

  return (
    <div className="min-h-screen bg-black text-white">
      <div className="p-4 border-b border-zinc-800">
        <div className="flex items-center justify-between max-w-3xl mx-auto">
          <h1 className="text-2xl font-semibold">Profile</h1>
        </div>
      </div>

      <div className="flex flex-col items-center px-4 py-8 md:py-16">
        <Avatar className="h-32 w-32">
          <AvatarImage src={user?.photoURL || '/omi-avatar.svg'} alt={user?.displayName || 'User'} />
          <AvatarFallback>{user?.displayName?.charAt(0) || 'U'}</AvatarFallback>
        </Avatar>
        <h2 className="text-2xl font-semibold mt-4">{user?.displayName || user?.email}</h2>
        <p className="text-gray-400">{user?.email}</p>

        <div className="mt-8">
          <label className="block text-gray-200 text-sm font-bold mb-2">
            Display Name:
          </label>
          <input
            className="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline bg-zinc-800 text-white border-zinc-700"
            type="text"
            placeholder="Display Name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </div>

        <button
          className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline mt-4"
          type="button"
          onClick={async () => {
            setLoading(true);
            try {
              if (auth.currentUser) {
                await updateProfile(auth.currentUser, {
                  displayName: displayName,
                });
                toast.success('Profile updated successfully!');
              } else {
                toast.error('No user is currently signed in.');
              }
            } catch (error: any) {
              console.error('Error updating profile:', error);
              toast.error('Failed to update profile.');
            } finally {
              setLoading(false);
            }
          }}
          disabled={loading}
        >
          {loading ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </div>
  );
};

export default ProfilePage;
